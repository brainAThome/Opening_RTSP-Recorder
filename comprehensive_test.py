#!/usr/bin/env python3
"""Comprehensive test script for RTSP Recorder v1.1.0 BETA"""

import sys
import os
import json
import ast
import re
from pathlib import Path
from datetime import datetime

# Test results
results = {
    "timestamp": datetime.now().isoformat(),
    "version": "v1.1.0 BETA",
    "tests": {},
    "summary": {"passed": 0, "failed": 0, "warnings": 0}
}

def log_test(category, test_name, status, details=""):
    if category not in results["tests"]:
        results["tests"][category] = []
    results["tests"][category].append({
        "test": test_name,
        "status": status,
        "details": details
    })
    if status == "PASS":
        results["summary"]["passed"] += 1
    elif status == "FAIL":
        results["summary"]["failed"] += 1
    else:
        results["summary"]["warnings"] += 1
    print(f"[{status}] {category}/{test_name}: {details[:80] if details else 'OK'}")

# ============================================
# 1. SYNTAX TESTS
# ============================================
print("\n" + "="*60)
print("1. SYNTAX TESTS")
print("="*60)

base_path = Path("/config/custom_components/rtsp_recorder")
py_files = list(base_path.glob("*.py"))

for py_file in py_files:
    try:
        with open(py_file, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        log_test("Syntax", py_file.name, "PASS")
    except SyntaxError as e:
        log_test("Syntax", py_file.name, "FAIL", f"Line {e.lineno}: {e.msg}")
    except Exception as e:
        log_test("Syntax", py_file.name, "FAIL", str(e))

# ============================================
# 2. UTF-8 ENCODING TESTS
# ============================================
print("\n" + "="*60)
print("2. UTF-8 ENCODING TESTS")
print("="*60)

for py_file in py_files:
    try:
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # Check for BOM
        if content.startswith('\ufeff'):
            log_test("UTF-8", py_file.name, "WARN", "Contains BOM marker")
        # Check for non-ASCII
        non_ascii = [c for c in content if ord(c) > 127]
        if non_ascii:
            log_test("UTF-8", py_file.name, "PASS", f"Contains {len(non_ascii)} non-ASCII chars (OK for German)")
        else:
            log_test("UTF-8", py_file.name, "PASS", "Pure ASCII")
    except UnicodeDecodeError as e:
        log_test("UTF-8", py_file.name, "FAIL", str(e))

# ============================================
# 3. IMPORT DEPENDENCY TESTS
# ============================================
print("\n" + "="*60)
print("3. IMPORT DEPENDENCY TESTS")
print("="*60)

# Check internal imports
internal_modules = ['const', 'database', 'people_db', 'helpers', 'analysis_helpers', 
                    'face_matching', 'recorder', 'retention', 'analysis', 'config_flow', 
                    'services', 'websocket_handlers']

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all from . imports
    internal_imports = re.findall(r'from \.([\w_]+) import', content)
    for imp in internal_imports:
        if imp in internal_modules or imp == '':
            log_test("Imports", f"{py_file.name} -> .{imp}", "PASS")
        else:
            log_test("Imports", f"{py_file.name} -> .{imp}", "WARN", "Unknown internal module")

# ============================================
# 4. FUNCTION/CLASS DEFINITION TESTS
# ============================================
print("\n" + "="*60)
print("4. FUNCTION & CLASS DEFINITIONS")
print("="*60)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        async_functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        
        log_test("Definitions", py_file.name, "PASS", 
                 f"{len(functions)} funcs, {len(async_functions)} async, {len(classes)} classes")
    except Exception as e:
        log_test("Definitions", py_file.name, "FAIL", str(e))

# ============================================
# 5. INDENTATION TESTS
# ============================================
print("\n" + "="*60)
print("5. INDENTATION TESTS")
print("="*60)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    issues = []
    for i, line in enumerate(lines, 1):
        if line.strip() and not line.startswith('#'):
            # Check for tabs
            if '\t' in line:
                issues.append(f"Line {i}: Tab character found")
            # Check for trailing whitespace
            if line.rstrip() != line.rstrip('\n').rstrip('\r'):
                pass  # Trailing whitespace (not critical)
    
    if issues:
        log_test("Indentation", py_file.name, "WARN", f"{len(issues)} issues")
    else:
        log_test("Indentation", py_file.name, "PASS")

# ============================================
# 6. WEBSOCKET HANDLER TESTS
# ============================================
print("\n" + "="*60)
print("6. WEBSOCKET HANDLER TESTS")
print("="*60)

ws_file = base_path / "websocket_handlers.py"
with open(ws_file, 'r', encoding='utf-8') as f:
    ws_content = f.read()

# Find all websocket handlers
ws_handlers = re.findall(r'async def (ws_\w+)\(', ws_content)
log_test("WebSocket", "Handler count", "PASS", f"{len(ws_handlers)} handlers found")

# Check each handler has proper registration
registrations = re.findall(r'async_register_command\(hass, (ws_\w+)\)', ws_content)
log_test("WebSocket", "Registrations", "PASS" if len(registrations) == len(ws_handlers) else "WARN",
         f"{len(registrations)} registrations for {len(ws_handlers)} handlers")

# List all handlers
for handler in ws_handlers:
    if handler in registrations:
        log_test("WebSocket", handler, "PASS", "Registered")
    else:
        log_test("WebSocket", handler, "FAIL", "NOT registered")

# ============================================
# 7. ERROR HANDLING TESTS
# ============================================
print("\n" + "="*60)
print("7. ERROR HANDLING TESTS")
print("="*60)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        
        # Count try/except blocks
        try_blocks = len([node for node in ast.walk(tree) if isinstance(node, ast.Try)])
        
        # Check for bare except
        bare_except = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bare_except += 1
        
        status = "PASS" if bare_except == 0 else "WARN"
        log_test("ErrorHandling", py_file.name, status,
                 f"{try_blocks} try blocks, {bare_except} bare except")
    except Exception as e:
        log_test("ErrorHandling", py_file.name, "FAIL", str(e))

# ============================================
# 8. LOOP SAFETY TESTS
# ============================================
print("\n" + "="*60)
print("8. LOOP SAFETY TESTS")
print("="*60)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        
        for_loops = len([node for node in ast.walk(tree) if isinstance(node, ast.For)])
        while_loops = len([node for node in ast.walk(tree) if isinstance(node, ast.While)])
        async_for = len([node for node in ast.walk(tree) if isinstance(node, ast.AsyncFor)])
        
        # Check for infinite loop patterns (while True without break)
        infinite_risk = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                if isinstance(node.test, ast.Constant) and node.test.value == True:
                    # Check if there's a break in the body
                    has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                    if not has_break:
                        infinite_risk += 1
        
        status = "PASS" if infinite_risk == 0 else "WARN"
        log_test("Loops", py_file.name, status,
                 f"{for_loops} for, {while_loops} while, {async_for} async for, {infinite_risk} potential infinite")
    except Exception as e:
        log_test("Loops", py_file.name, "FAIL", str(e))

# ============================================
# 9. JAVASCRIPT CARD TESTS
# ============================================
print("\n" + "="*60)
print("9. JAVASCRIPT CARD TESTS")
print("="*60)

js_file = Path("/config/www/rtsp-recorder-card.js")
if js_file.exists():
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    # Basic checks
    log_test("JavaScript", "File exists", "PASS", f"{len(js_content)} bytes")
    
    # Check for class definition
    if "class RTSPRecorderCard" in js_content:
        log_test("JavaScript", "Class definition", "PASS")
    else:
        log_test("JavaScript", "Class definition", "FAIL", "RTSPRecorderCard not found")
    
    # Check for customElements registration
    if "customElements.define" in js_content:
        log_test("JavaScript", "Custom element registration", "PASS")
    else:
        log_test("JavaScript", "Custom element registration", "FAIL")
    
    # Check innerHTML vs textContent usage
    innerHTML_count = len(re.findall(r'\.innerHTML\s*=', js_content))
    textContent_count = len(re.findall(r'\.textContent\s*=', js_content))
    log_test("JavaScript", "DOM manipulation", "PASS" if textContent_count > 0 else "WARN",
             f"{innerHTML_count} innerHTML, {textContent_count} textContent")
    
    # Check for _escapeHtml usage
    escapeHtml_count = len(re.findall(r'_escapeHtml\(', js_content))
    log_test("JavaScript", "XSS Protection", "PASS" if escapeHtml_count > 10 else "WARN",
             f"{escapeHtml_count} _escapeHtml calls")
    
    # Count methods
    methods = re.findall(r'^\s+(async\s+)?(\w+)\s*\([^)]*\)\s*\{', js_content, re.MULTILINE)
    log_test("JavaScript", "Methods", "PASS", f"{len(methods)} methods found")
    
    # Check for WebSocket calls
    ws_calls = re.findall(r"type:\s*['\"]rtsp_recorder/(\w+)['\"]", js_content)
    log_test("JavaScript", "WebSocket calls", "PASS", f"{len(set(ws_calls))} unique WS endpoints used")

# ============================================
# 10. MANIFEST & CONFIG TESTS
# ============================================
print("\n" + "="*60)
print("10. MANIFEST & CONFIG TESTS")
print("="*60)

manifest_file = base_path / "manifest.json"
if manifest_file.exists():
    with open(manifest_file, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    required_fields = ['domain', 'name', 'version', 'documentation', 'codeowners']
    for field in required_fields:
        if field in manifest:
            log_test("Manifest", field, "PASS", str(manifest[field])[:50])
        else:
            log_test("Manifest", field, "FAIL", "Missing")
    
    # Check requirements
    if 'requirements' in manifest:
        log_test("Manifest", "requirements", "PASS", f"{len(manifest['requirements'])} dependencies")

# ============================================
# 11. DATABASE SCHEMA TESTS
# ============================================
print("\n" + "="*60)
print("11. DATABASE SCHEMA TESTS")
print("="*60)

db_file = base_path / "database.py"
with open(db_file, 'r', encoding='utf-8') as f:
    db_content = f.read()

# Find CREATE TABLE statements
tables = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', db_content)
log_test("Database", "Tables defined", "PASS", f"{len(tables)} tables: {', '.join(tables)}")

# Check for SQL injection protection (parameterized queries)
param_queries = len(re.findall(r'\?\s*[,\)]', db_content))
string_format = len(re.findall(r'f["\'].*\{.*\}.*["\'].*execute', db_content))
log_test("Database", "Query safety", "PASS" if param_queries > 10 else "WARN",
         f"{param_queries} parameterized, {string_format} f-string in execute")

# ============================================
# 12. SECURITY TESTS
# ============================================
print("\n" + "="*60)
print("12. SECURITY TESTS")
print("="*60)

# Check for hardcoded credentials
for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for hardcoded passwords/tokens
    suspicious = re.findall(r'(password|secret|token|api_key)\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE)
    if suspicious:
        log_test("Security", f"{py_file.name} credentials", "WARN", f"{len(suspicious)} potential hardcoded credentials")
    else:
        log_test("Security", f"{py_file.name} credentials", "PASS")

# Check for eval/exec usage
for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    dangerous = len(re.findall(r'\b(eval|exec)\s*\(', content))
    if dangerous:
        log_test("Security", f"{py_file.name} eval/exec", "WARN", f"{dangerous} dangerous calls")
    else:
        log_test("Security", f"{py_file.name} eval/exec", "PASS")

# ============================================
# 13. LINE COUNT & COMPLEXITY
# ============================================
print("\n" + "="*60)
print("13. CODE METRICS")
print("="*60)

total_py_lines = 0
total_js_lines = 0

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        lines = len(f.readlines())
    total_py_lines += lines
    log_test("Metrics", f"{py_file.name} LOC", "PASS", f"{lines} lines")

if js_file.exists():
    with open(js_file, 'r', encoding='utf-8') as f:
        total_js_lines = len(f.readlines())
    log_test("Metrics", "rtsp-recorder-card.js LOC", "PASS", f"{total_js_lines} lines")

log_test("Metrics", "Total Python LOC", "PASS", f"{total_py_lines} lines")
log_test("Metrics", "Total JavaScript LOC", "PASS", f"{total_js_lines} lines")
log_test("Metrics", "Total LOC", "PASS", f"{total_py_lines + total_js_lines} lines")

# ============================================
# SUMMARY
# ============================================
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"PASSED:   {results['summary']['passed']}")
print(f"WARNINGS: {results['summary']['warnings']}")
print(f"FAILED:   {results['summary']['failed']}")
print(f"TOTAL:    {results['summary']['passed'] + results['summary']['warnings'] + results['summary']['failed']}")

# Save results
with open('/tmp/test_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nResults saved to /tmp/test_results.json")
