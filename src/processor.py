# processor.py
import os
import time
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
import yaml
import json
import re
from pathlib import Path

VAULT_PATH = os.getenv("VAULT_PATH", "/obsidian")
MISTRAL_API_URL = "https://api.mistral.ai/v1/"
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

class NoteProcessor:
    def __init__(self):
        self.observer = Observer()
        self.processed_hashes = set()
        self.load_processed_hashes()

    def load_processed_hashes(self):
        """Load previously processed file hashes"""
        hash_file = os.path.join(VAULT_PATH, ".ai-processed")
        if os.path.exists(hash_file):
            with open(hash_file, 'r') as f:
                self.processed_hashes = set(f.read().splitlines())

    def save_processed_hash(self, filepath):
        """Save processed file hash"""
        file_hash = hashlib.md5(open(filepath, 'rb').read()).hexdigest()
        self.processed_hashes.add(file_hash)
        hash_file = os.path.join(VAULT_PATH, ".ai-processed")
        with open(hash_file, 'w') as f:
            f.write("\n".join(self.processed_hashes))

    def file_hash(self, filepath):
        """Calculate file hash"""
        return hashlib.md5(open(filepath, 'rb').read()).hexdigest()

    def should_process(self, filepath):
        """Check if file should be processed"""
        if not filepath.endswith('.md'):
            return False
        if filepath.startswith('.') or 'Templates' in filepath:
            return False
        file_hash = self.file_hash(filepath)
        return file_hash not in self.processed_hashes

    def extract_content(self, filepath):
        """Extract content from markdown file, separating frontmatter"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter_end = content.find('\n---\n')
        if frontmatter_end > 0:
            existing_frontmatter = content[:frontmatter_end + 5]
            body = content[frontmatter_end + 5:]
        else:
            existing_frontmatter = ""
            body = content

        return existing_frontmatter, body

    def call_mistral(self, prompt, model="mistral-medium", temperature=0.3):
        """Call Mistral API"""
        response = requests.post(
            f"{MISTRAL_API_URL}chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature
            }
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"Mistral API error: {response.text}")
            return None

    def process_note(self, filepath):
        """Process a single note file"""
        try:
            print(f"Processing: {filepath}")

            # Extract existing content
            existing_frontmatter, body = self.extract_content(filepath)

            # Skip if no body content
            if len(body.strip()) < 20:
                print(f"Skipping {filepath} - too short")
                return False

            # Extract text (remove markdown formatting for AI)
            clean_text = self.clean_markdown(body)

            # Get AI analysis
            analysis = self.analyze_note(clean_text, filepath)

            if not analysis:
                print(f"Failed to analyze {filepath}")
                return False

            # Generate new frontmatter
            new_frontmatter = self.generate_frontmatter(analysis, existing_frontmatter)

            # Write updated file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_frontmatter + "\n\n" + body)

            # Save hash
            self.save_processed_hash(filepath)
            print(f"Processed: {filepath}")
            return True

        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            return False

    def clean_markdown(self, text):
        """Remove markdown formatting for cleaner AI input"""
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        # Remove inline code
        text = re.sub(r'`[^`]+`', '', text)
        # Remove links (keep the text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove images
        text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
        # Remove bold/italic
        text = re.sub(r'[\*_]{1,2}([^\*_]+)[\*_]{1,2}', r'\1', text)
        # Remove headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    def analyze_note(self, text, filepath):
        """Analyze note content with Mistral AI"""
        # Limit text length for API
        if len(text) > 8000:
            text = text[:8000] + "\n\n... (truncated)"

        prompt = f"""Analyze the following Obsidian note and provide structured output:

        Note content:
        {text}

        Provide output in this exact JSON format:
        {{
            "categories": ["category1", "category2"],
            "summary": "Brief summary of the note",
            "tags": ["tag1", "tag2"],
            "related_notes": ["Note Name 1", "Note Name 2"]
        }}

        Guidelines:
        - categories: 2-4 broad topics this note belongs to
        - summary: 1-2 sentences max
        - tags: 3-6 specific tags (single words or short phrases)
        - related_notes: Names of existing notes this might link to (if any)
        - Use lowercase for categories and tags
        - Be concise but accurate"""

        result = self.call_mistral(prompt, temperature=0.2)
        if not result:
            return None

        # Parse JSON from result
        try:
            # Clean up the response to extract JSON
            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            json_str = result[json_start:json_end]
            return json.loads(json_str)
        except:
            print(f"Failed to parse AI response: {result}")
            return None

    def generate_frontmatter(self, analysis, existing_frontmatter):
        """Generate YAML frontmatter with AI analysis"""
        # Parse existing frontmatter
        existing = {}
        if existing_frontmatter:
            try:
                existing = yaml.safe_load(existing_frontmatter)
            except:
                pass

        # Merge with AI analysis
        frontmatter = {
            "type": "note",
            "categories": analysis.get("categories", []),
            "summary": analysis.get("summary", ""),
            "tags": analysis.get("tags", []),
            "ai-processed": True,
            "ai-processed-at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Preserve existing fields
        if existing:
            for key, value in existing.items():
                if key not in frontmatter:
                    frontmatter[key] = value

        return "---\n" + yaml.dump(frontmatter, sort_keys=False, default_flow_style=False).strip() + "\n---"

    def start_watching(self):
        """Start watching the vault directory"""
        event_handler = FileSystemEventHandler()
        event_handler.on_modified = lambda event: self.process_file(event.src_path)
        event_handler.on_created = lambda event: self.process_file(event.src_path)

        self.observer.schedule(event_handler, VAULT_PATH, recursive=True)
        self.observer.start()
        print(f"Watching {VAULT_PATH} for new/modified notes...")

        # Process existing notes on startup
        self.process_existing_notes()

    def process_file(self, filepath):
        """Process a single file if it should be processed"""
        if self.should_process(filepath):
            self.process_note(filepath)

    def process_existing_notes(self):
        """Process all existing notes on startup"""
        print("Processing existing notes...")
        for root, dirs, files in os.walk(VAULT_PATH):
            # Skip hidden directories and templates
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'Templates']
            for file in files:
                if file.endswith('.md'):
                    filepath = os.path.join(root, file)
                    self.process_file(filepath)

if __name__ == "__main__":
    processor = NoteProcessor()
    processor.start_watching()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        processor.observer.stop()
    processor.observer.join()
