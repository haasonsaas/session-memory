#!/usr/bin/env python3

"""
session-memory - Persistent context tracking for AI agents

A lightweight CLI tool that maintains session state across AI interactions,
storing file reads, changes, test results, and contextual notes in SQLite.
"""

import argparse
import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import hashlib
import subprocess
import re

# Configuration
DEFAULT_DB_PATH = os.path.expanduser("~/.session-memory.db")
SCHEMA_VERSION = 1

class SessionMemory:
    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with schema"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Create tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_path TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                status TEXT DEFAULT 'active'
            );
            
            CREATE TABLE IF NOT EXISTS file_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                file_path TEXT NOT NULL,
                file_hash TEXT,
                read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                context TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            
            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL, -- 'create', 'modify', 'delete'
                description TEXT,
                before_hash TEXT,
                after_hash TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                command TEXT NOT NULL,
                result TEXT NOT NULL, -- 'pass', 'fail', 'error'
                output TEXT,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                content TEXT NOT NULL,
                tags TEXT, -- JSON array of tags
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                file_path TEXT,
                context TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            
            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_path);
            CREATE INDEX IF NOT EXISTS idx_file_reads_session ON file_reads(session_id);
            CREATE INDEX IF NOT EXISTS idx_changes_session ON changes(session_id);
            CREATE INDEX IF NOT EXISTS idx_tests_session ON tests(session_id);
            CREATE INDEX IF NOT EXISTS idx_notes_session ON notes(session_id);
            CREATE INDEX IF NOT EXISTS idx_errors_session ON errors(session_id);
        """)
        
        conn.commit()
        conn.close()
    
    def get_current_session(self):
        """Get or create current session based on working directory"""
        project_path = os.getcwd()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Try to find active session for current project
        cursor.execute("""
            SELECT id FROM sessions 
            WHERE project_path = ? AND status = 'active'
            ORDER BY last_active DESC LIMIT 1
        """, (project_path,))
        
        result = cursor.fetchone()
        if result:
            session_id = result[0]
            # Update last_active
            cursor.execute("""
                UPDATE sessions SET last_active = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session_id,))
        else:
            # Create new session
            cursor.execute("""
                INSERT INTO sessions (project_path, description)
                VALUES (?, ?)
            """, (project_path, f"Session for {os.path.basename(project_path)}"))
            session_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return session_id
    
    def file_hash(self, file_path):
        """Calculate MD5 hash of file content"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None
    
    def infer_context(self, file_path):
        """Infer context based on file type and content"""
        try:
            file_path = Path(file_path)
            
            # File type contexts
            contexts = {
                '.py': 'Examining Python code',
                '.js': 'Examining JavaScript code', 
                '.ts': 'Examining TypeScript code',
                '.jsx': 'Examining React component',
                '.tsx': 'Examining React TypeScript component',
                '.css': 'Examining styles',
                '.scss': 'Examining SCSS styles',
                '.html': 'Examining HTML markup',
                '.json': 'Examining configuration/data',
                '.md': 'Examining documentation',
                '.yml': 'Examining YAML configuration',
                '.yaml': 'Examining YAML configuration',
                '.toml': 'Examining TOML configuration',
                '.dockerfile': 'Examining Docker configuration',
                '.sql': 'Examining database schema/queries',
                '.sh': 'Examining shell script',
                '.bash': 'Examining bash script',
                '.zsh': 'Examining zsh script'
            }
            
            # Special filename patterns
            special_files = {
                'package.json': 'Examining project dependencies and scripts',
                'requirements.txt': 'Examining Python dependencies',
                'cargo.toml': 'Examining Rust project configuration',
                'dockerfile': 'Examining Docker container setup',
                'makefile': 'Examining build configuration',
                'readme': 'Reading project documentation',
                'changelog': 'Examining project history',
                'license': 'Examining project license',
                '.gitignore': 'Examining git ignore patterns',
                '.env': 'Examining environment configuration',
                'config': 'Examining configuration file'
            }
            
            filename_lower = file_path.name.lower()
            
            # Check special files first
            for pattern, context in special_files.items():
                if pattern in filename_lower:
                    return context
            
            # Check file extensions
            suffix = file_path.suffix.lower()
            if suffix in contexts:
                context = contexts[suffix]
                
                # Try to read first few lines for more specific context
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        first_lines = ''.join(f.readlines()[:10]).lower()
                        
                        # Detect specific patterns
                        if 'test' in filename_lower or 'spec' in filename_lower:
                            context = f"Examining {suffix[1:]} test file"
                        elif 'api' in filename_lower or 'endpoint' in filename_lower:
                            context = f"Examining {suffix[1:]} API code"
                        elif 'component' in filename_lower:
                            context = f"Examining {suffix[1:]} component"
                        elif 'util' in filename_lower or 'helper' in filename_lower:
                            context = f"Examining {suffix[1:]} utility functions"
                        elif 'config' in filename_lower or 'setting' in filename_lower:
                            context = f"Examining {suffix[1:]} configuration"
                        elif re.search(r'class\s+\w+', first_lines):
                            context = f"Examining {suffix[1:]} class definition"
                        elif re.search(r'function\s+\w+|def\s+\w+', first_lines):
                            context = f"Examining {suffix[1:]} function definitions"
                        elif 'import' in first_lines or 'from' in first_lines:
                            context = f"Examining {suffix[1:]} module imports and setup"
                            
                except:
                    pass
                    
                return context
            
            # Fallback
            if file_path.is_dir():
                return "Examining directory structure"
            else:
                return f"Examining {suffix[1:] if suffix else 'file'}"
                
        except:
            return "Examining file"
    
    def get_session_analytics(self):
        """Get analytics for current session"""
        session_id = self.get_current_session()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        analytics = {}
        
        # Session duration
        cursor.execute("""
            SELECT started_at, last_active FROM sessions WHERE id = ?
        """, (session_id,))
        result = cursor.fetchone()
        if result:
            started = datetime.fromisoformat(result[0].replace('Z', '+00:00'))
            last_active = datetime.fromisoformat(result[1].replace('Z', '+00:00'))
            analytics['duration_minutes'] = int((last_active - started).total_seconds() / 60)
        
        # Activity counts
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM file_reads WHERE session_id = ?) as reads,
                (SELECT COUNT(*) FROM changes WHERE session_id = ?) as changes,
                (SELECT COUNT(*) FROM tests WHERE session_id = ?) as tests,
                (SELECT COUNT(*) FROM notes WHERE session_id = ?) as notes,
                (SELECT COUNT(*) FROM errors WHERE session_id = ?) as errors
        """, (session_id, session_id, session_id, session_id, session_id))
        
        result = cursor.fetchone()
        if result:
            analytics.update({
                'files_read': result[0],
                'changes_made': result[1], 
                'tests_run': result[2],
                'notes_added': result[3],
                'errors_logged': result[4]
            })
        
        # Test success rate
        cursor.execute("""
            SELECT result, COUNT(*) FROM tests 
            WHERE session_id = ? GROUP BY result
        """, (session_id,))
        
        test_results = dict(cursor.fetchall())
        total_tests = sum(test_results.values())
        if total_tests > 0:
            analytics['test_success_rate'] = test_results.get('pass', 0) / total_tests * 100
        
        # Most active file types
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN file_path LIKE '%.py' THEN 'Python'
                    WHEN file_path LIKE '%.js' THEN 'JavaScript'
                    WHEN file_path LIKE '%.ts' THEN 'TypeScript'
                    WHEN file_path LIKE '%.jsx' THEN 'React'
                    WHEN file_path LIKE '%.tsx' THEN 'React TS'
                    WHEN file_path LIKE '%.css' THEN 'CSS'
                    WHEN file_path LIKE '%.md' THEN 'Markdown'
                    WHEN file_path LIKE '%.json' THEN 'JSON'
                    ELSE 'Other'
                END as file_type,
                COUNT(*) as count
            FROM (
                SELECT file_path FROM file_reads WHERE session_id = ?
                UNION ALL
                SELECT file_path FROM changes WHERE session_id = ?
            ) 
            GROUP BY file_type
            ORDER BY count DESC
            LIMIT 5
        """, (session_id, session_id))
        
        analytics['file_types'] = dict(cursor.fetchall())
        
        conn.close()
        return analytics
    
    def log_read(self, file_path, context=None):
        """Log that a file was read"""
        session_id = self.get_current_session()
        file_path = os.path.abspath(file_path)
        file_hash = self.file_hash(file_path)
        
        # Use inferred context if none provided
        if context is None:
            context = self.infer_context(file_path)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO file_reads (session_id, file_path, file_hash, context)
            VALUES (?, ?, ?, ?)
        """, (session_id, file_path, file_hash, context))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def log_change(self, file_path, change_type, description=None):
        """Log a file change"""
        session_id = self.get_current_session()
        file_path = os.path.abspath(file_path)
        
        # Get before and after hashes if file exists
        before_hash = None
        after_hash = None
        
        if change_type in ['modify', 'delete']:
            # For modify/delete, we should have recorded the file before
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_hash FROM file_reads 
                WHERE session_id = ? AND file_path = ?
                ORDER BY read_at DESC LIMIT 1
            """, (session_id, file_path))
            result = cursor.fetchone()
            if result:
                before_hash = result[0]
            conn.close()
        
        if change_type in ['create', 'modify']:
            after_hash = self.file_hash(file_path)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO changes (session_id, file_path, change_type, description, before_hash, after_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, file_path, change_type, description, before_hash, after_hash))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def log_test(self, command, result, output=None):
        """Log test execution"""
        session_id = self.get_current_session()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO tests (session_id, command, result, output)
            VALUES (?, ?, ?, ?)
        """, (session_id, command, result, output))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def add_note(self, content, tags=None):
        """Add a contextual note"""
        session_id = self.get_current_session()
        tags_json = json.dumps(tags) if tags else None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO notes (session_id, content, tags)
            VALUES (?, ?, ?)
        """, (session_id, content, tags_json))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def log_error(self, error_type, error_message, file_path=None, context=None):
        """Log an error"""
        session_id = self.get_current_session()
        file_path = os.path.abspath(file_path) if file_path else None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO errors (session_id, error_type, error_message, file_path, context)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, error_type, error_message, file_path, context))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def query_session(self, query_type=None, limit=50):
        """Query session data"""
        session_id = self.get_current_session()
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if query_type == "reads":
            cursor.execute("""
                SELECT file_path, read_at, context
                FROM file_reads
                WHERE session_id = ?
                ORDER BY read_at DESC
                LIMIT ?
            """, (session_id, limit))
        elif query_type == "changes":
            cursor.execute("""
                SELECT file_path, change_type, description, changed_at
                FROM changes
                WHERE session_id = ?
                ORDER BY changed_at DESC
                LIMIT ?
            """, (session_id, limit))
        elif query_type == "tests":
            cursor.execute("""
                SELECT command, result, output, run_at
                FROM tests
                WHERE session_id = ?
                ORDER BY run_at DESC
                LIMIT ?
            """, (session_id, limit))
        elif query_type == "notes":
            cursor.execute("""
                SELECT content, tags, created_at
                FROM notes
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (session_id, limit))
        elif query_type == "errors":
            cursor.execute("""
                SELECT error_type, error_message, file_path, context, occurred_at
                FROM errors
                WHERE session_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
            """, (session_id, limit))
        else:
            # Summary query
            cursor.execute("""
                SELECT 
                    'reads' as type, COUNT(*) as count
                FROM file_reads WHERE session_id = ?
                UNION ALL
                SELECT 'changes' as type, COUNT(*) as count
                FROM changes WHERE session_id = ?
                UNION ALL
                SELECT 'tests' as type, COUNT(*) as count
                FROM tests WHERE session_id = ?
                UNION ALL
                SELECT 'notes' as type, COUNT(*) as count
                FROM notes WHERE session_id = ?
                UNION ALL
                SELECT 'errors' as type, COUNT(*) as count
                FROM errors WHERE session_id = ?
            """, (session_id, session_id, session_id, session_id, session_id))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    
    def export_session(self, format_type="json"):
        """Export session data"""
        session_id = self.get_current_session()
        
        data = {
            "session_id": session_id,
            "exported_at": datetime.now().isoformat(),
            "reads": self.query_session("reads", limit=1000),
            "changes": self.query_session("changes", limit=1000),
            "tests": self.query_session("tests", limit=1000),
            "notes": self.query_session("notes", limit=1000),
            "errors": self.query_session("errors", limit=1000)
        }
        
        if format_type == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            return str(data)

def main():
    parser = argparse.ArgumentParser(description="AI Agent Session Memory")
    parser.add_argument("--db", help="Database path", default=DEFAULT_DB_PATH)
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize new session")
    init_parser.add_argument("--description", help="Session description")
    
    # Read command
    read_parser = subparsers.add_parser("read", help="Log file read")
    read_parser.add_argument("file_path", help="File that was read")
    read_parser.add_argument("--context", help="Context about why it was read")
    
    # Change command
    change_parser = subparsers.add_parser("change", help="Log file change")
    change_parser.add_argument("file_path", help="File that was changed")
    change_parser.add_argument("description", help="Description of change")
    change_parser.add_argument("--type", choices=["create", "modify", "delete"], 
                              default="modify", help="Type of change")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Log test execution")
    test_parser.add_argument("command", help="Test command that was run")
    test_parser.add_argument("result", choices=["pass", "fail", "error"], 
                            help="Test result")
    test_parser.add_argument("--output", help="Test output")
    
    # Note command
    note_parser = subparsers.add_parser("note", help="Add contextual note")
    note_parser.add_argument("content", help="Note content")
    note_parser.add_argument("--tags", nargs="*", help="Tags for the note")
    
    # Error command
    error_parser = subparsers.add_parser("error", help="Log error")
    error_parser.add_argument("type", help="Error type")
    error_parser.add_argument("message", help="Error message")
    error_parser.add_argument("--file", help="File where error occurred")
    error_parser.add_argument("--context", help="Additional context")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query session data")
    query_parser.add_argument("type", nargs="?", 
                             choices=["reads", "changes", "tests", "notes", "errors"],
                             help="Type of data to query")
    query_parser.add_argument("--limit", type=int, default=20, help="Limit results")
    query_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export session data")
    export_parser.add_argument("--format", choices=["json"], default="json",
                              help="Export format")
    export_parser.add_argument("--output", help="Output file (default: stdout)")
    
    # Analytics command
    analytics_parser = subparsers.add_parser("analytics", help="Show session analytics")
    analytics_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    sm = SessionMemory(args.db)
    
    if args.command == "init":
        session_id = sm.get_current_session()
        print(f"✅ Session {session_id} initialized for {os.getcwd()}")
    
    elif args.command == "read":
        entry_id = sm.log_read(args.file_path, args.context)
        print(f"📖 Logged read of {args.file_path} (ID: {entry_id})")
    
    elif args.command == "change":
        entry_id = sm.log_change(args.file_path, args.type, args.description)
        print(f"✏️  Logged {args.type} of {args.file_path} (ID: {entry_id})")
    
    elif args.command == "test":
        entry_id = sm.log_test(args.command, args.result, args.output)
        result_emoji = "✅" if args.result == "pass" else "❌" if args.result == "fail" else "⚠️"
        print(f"{result_emoji} Logged test: {args.command} -> {args.result} (ID: {entry_id})")
    
    elif args.command == "note":
        entry_id = sm.add_note(args.content, args.tags)
        print(f"📝 Added note (ID: {entry_id})")
    
    elif args.command == "error":
        entry_id = sm.log_error(args.type, args.message, args.file, args.context)
        print(f"🚨 Logged error: {args.type} (ID: {entry_id})")
    
    elif args.command == "query":
        results = sm.query_session(args.type, args.limit)
        
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            if args.type:
                print(f"\n📊 Last {len(results)} {args.type}:")
                for result in results:
                    if args.type == "reads":
                        print(f"  📖 {result['file_path']} ({result['read_at']})")
                        if result['context']:
                            print(f"     Context: {result['context']}")
                    elif args.type == "changes":
                        print(f"  ✏️  {result['change_type']}: {result['file_path']} ({result['changed_at']})")
                        if result['description']:
                            print(f"     {result['description']}")
                    elif args.type == "tests":
                        emoji = "✅" if result['result'] == "pass" else "❌" if result['result'] == "fail" else "⚠️"
                        print(f"  {emoji} {result['command']} -> {result['result']} ({result['run_at']})")
                    elif args.type == "notes":
                        print(f"  📝 {result['content']} ({result['created_at']})")
                        if result['tags']:
                            tags = json.loads(result['tags'])
                            print(f"     Tags: {', '.join(tags)}")
                    elif args.type == "errors":
                        print(f"  🚨 {result['error_type']}: {result['error_message']} ({result['occurred_at']})")
                        if result['file_path']:
                            print(f"     File: {result['file_path']}")
            else:
                print("\n📊 Session Summary:")
                for result in results:
                    print(f"  {result['type']}: {result['count']}")
    
    elif args.command == "export":
        data = sm.export_session(args.format)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(data)
            print(f"📤 Session exported to {args.output}")
        else:
            print(data)
    
    elif args.command == "analytics":
        analytics = sm.get_session_analytics()
        
        if args.json:
            print(json.dumps(analytics, indent=2))
        else:
            print("\n📊 Session Analytics")
            print("=" * 50)
            
            if 'duration_minutes' in analytics:
                duration = analytics['duration_minutes']
                if duration < 60:
                    print(f"⏱️  Session duration: {duration} minutes")
                else:
                    hours = duration // 60
                    minutes = duration % 60
                    print(f"⏱️  Session duration: {hours}h {minutes}m")
            
            print(f"📖 Files read: {analytics.get('files_read', 0)}")
            print(f"✏️  Changes made: {analytics.get('changes_made', 0)}")
            print(f"🧪 Tests run: {analytics.get('tests_run', 0)}")
            print(f"📝 Notes added: {analytics.get('notes_added', 0)}")
            print(f"🚨 Errors logged: {analytics.get('errors_logged', 0)}")
            
            if 'test_success_rate' in analytics:
                rate = analytics['test_success_rate']
                emoji = "✅" if rate >= 80 else "⚠️" if rate >= 60 else "❌"
                print(f"{emoji} Test success rate: {rate:.1f}%")
            
            if analytics.get('file_types'):
                print("\n🗂️  Most active file types:")
                for file_type, count in list(analytics['file_types'].items())[:5]:
                    print(f"   {file_type}: {count} files")
            
            # Productivity insights
            total_activity = (analytics.get('files_read', 0) + 
                            analytics.get('changes_made', 0) + 
                            analytics.get('tests_run', 0))
            
            if total_activity > 0 and analytics.get('duration_minutes', 0) > 0:
                activity_rate = total_activity / analytics['duration_minutes']
                print(f"\n⚡ Activity rate: {activity_rate:.1f} actions/minute")
                
                if activity_rate > 2:
                    print("   🔥 High productivity session!")
                elif activity_rate > 1:
                    print("   👍 Good productivity")
                else:
                    print("   🤔 Consider taking breaks between focused work")

if __name__ == "__main__":
    main()
