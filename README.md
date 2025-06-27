# Session Memory

Lightweight CLI tool for AI agent session context persistence using SQLite.

## Overview

`session-memory` helps AI agents maintain context across interactions by storing file reads, changes, test results, notes, and errors in a persistent SQLite database. This enables agents to remember what they've done in previous tool calls and build upon past work.

## Features

- **Persistent context**: Maintains session state across AI interactions
- **Project-aware**: Automatically creates sessions based on working directory
- **Comprehensive logging**: Tracks file reads, changes, tests, notes, and errors
- **Temporal tracking**: All entries include timestamps and context
- **Change detection**: Uses file hashes to track modifications
- **Query interface**: Easy retrieval of session data
- **Export capabilities**: JSON export for integration with other tools

## Installation

```bash
# Clone the repository
git clone https://github.com/haasonsaas/session-memory.git
cd session-memory

# Make executable and add to PATH
chmod +x session-memory
cp session-memory /usr/local/bin/  # or add to your PATH
```

## Usage

### Initialize a session
```bash
session-memory init
```

### Log file reads
```bash
session-memory read src/main.py --context "Examining the main application logic"
```

### Log changes
```bash
session-memory change src/utils.py "Added error handling" --type modify
session-memory change src/new-feature.py "Created new feature" --type create
```

### Log test results
```bash
session-memory test "npm test" pass --output "All 42 tests passed"
session-memory test "pytest" fail --output "3 tests failed in authentication module"
```

### Add contextual notes
```bash
session-memory note "User wants to implement OAuth authentication"
session-memory note "Performance bottleneck identified in database queries" --tags performance database
```

### Log errors
```bash
session-memory error "ImportError" "Module 'requests' not found" --file src/api.py --context "Running API tests"
```

### Query session data
```bash
# View session summary
session-memory query

# View recent changes
session-memory query changes

# View file reads with context
session-memory query reads --limit 10

# View test results
session-memory query tests

# View notes
session-memory query notes

# View errors
session-memory query errors
```

### Export session data
```bash
# Export to stdout
session-memory export --format json

# Export to file
session-memory export --format json --output session-data.json
```

## Database Schema

The tool uses SQLite with the following tables:

- **sessions**: Session metadata and project information
- **file_reads**: Files that were read with context and timestamps
- **changes**: File modifications with before/after hashes
- **tests**: Test executions with results and output
- **notes**: Contextual information and observations
- **errors**: Error occurrences with context

## AI Agent Integration

This tool is designed specifically for AI agents that need to maintain context across multiple tool invocations. Typical workflow:

1. **Before reading files**: Log with context about why you're reading them
2. **After making changes**: Record what was changed and why
3. **After running tests**: Log results and any failures
4. **Throughout development**: Add notes about user requirements, decisions made
5. **When errors occur**: Log them for pattern recognition

## Examples

### Typical AI agent workflow
```bash
# Start working on a project
session-memory init

# Read files to understand codebase
session-memory read package.json --context "Understanding project dependencies"
session-memory read src/index.js --context "Examining entry point"

# Make changes
session-memory change src/api.js "Added input validation" --type modify
session-memory change tests/api.test.js "Added validation tests" --type create

# Run tests
session-memory test "npm test" pass --output "All tests passing"

# Add contextual notes
session-memory note "Implemented input validation as requested by user"

# Query what we've done
session-memory query changes
```

### Error tracking
```bash
session-memory error "SyntaxError" "Unexpected token '}'" --file src/utils.js --context "After refactoring function"
session-memory error "TestFailure" "Expected 200, got 404" --context "API endpoint testing"
```

## Configuration

- **Database location**: `~/.session-memory.db` (configurable with `--db` flag)
- **Session detection**: Based on current working directory
- **Automatic timestamps**: All entries include creation timestamps

## Requirements

- Python 3.6+
- No external dependencies (uses built-in sqlite3)

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! This tool is specifically designed for AI agent workflows, so improvements should focus on enhancing agent productivity and context retention.