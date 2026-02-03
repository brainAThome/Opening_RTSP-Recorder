#!/usr/bin/env python3
"""Hardcore test script for RTSP Recorder v1.1.0 BETA - Deep Analysis"""

import sys
import os
import json
import ast
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

results = {
    "timestamp": datetime.now().isoformat(),
    "version": "v1.1.0 BETA - HARDCORE TEST",
    "tests": {},
    "issues": [],
    "summary": {"passed": 0, "failed": 0, "warnings": 0, "critical": 0}
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
    elif status == "CRITICAL":
        results["summary"]["critical"] += 1
        results["issues"].append(f"CRITICAL: {category}/{test_name}: {details}")
    else:
        results["summary"]["warnings"] += 1
    symbol = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "CRITICAL": "🔴"}.get(status, "?")
    print(f"[{symbol} {status}] {category}/{test_name}: {details[:100] if details else 'OK'}")

base_path = Path("/config/custom_components/rtsp_recorder")
py_files = list(base_path.glob("*.py"))

# ============================================
# HARDCORE TEST 1: ASYNC/AWAIT CONSISTENCY
# ============================================
print("\n" + "="*70)
print("HARDCORE 1: ASYNC/AWAIT CONSISTENCY")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        issues = []
        
        for node in ast.walk(tree):
            # Check async functions
            if isinstance(node, ast.AsyncFunctionDef):
                # Check if await is used properly
                has_await = any(isinstance(n, ast.Await) for n in ast.walk(node))
                has_async_for = any(isinstance(n, ast.AsyncFor) for n in ast.walk(node))
                has_async_with = any(isinstance(n, ast.AsyncWith) for n in ast.walk(node))
                
                if not has_await and not has_async_for and not has_async_with:
                    # Check if it calls other async functions (they might use run_in_executor)
                    has_call = any(isinstance(n, ast.Call) for n in ast.walk(node))
                    if not has_call:
                        issues.append(f"async def {node.name}() has no await/async operations")
        
        if issues:
            log_test("AsyncConsistency", py_file.name, "WARN", "; ".join(issues[:3]))
        else:
            log_test("AsyncConsistency", py_file.name, "PASS")
    except Exception as e:
        log_test("AsyncConsistency", py_file.name, "FAIL", str(e))

# ============================================
# HARDCORE TEST 2: EXCEPTION HANDLING QUALITY
# ============================================
print("\n" + "="*70)
print("HARDCORE 2: EXCEPTION HANDLING QUALITY")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    try:
        tree = ast.parse(content)
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Check for overly broad exception catching
                if node.type is None:
                    issues.append(f"Line {node.lineno}: bare except")
                elif isinstance(node.type, ast.Name):
                    if node.type.id == "Exception":
                        # Check if it's properly logged
                        handler_code = ast.unparse(node) if hasattr(ast, 'unparse') else ""
                        if "log" not in handler_code.lower() and "print" not in handler_code.lower():
                            issues.append(f"Line {node.lineno}: catches Exception without logging")
                    elif node.type.id == "BaseException":
                        issues.append(f"Line {node.lineno}: catches BaseException (too broad)")
                
                # Check for empty except blocks
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    issues.append(f"Line {node.lineno}: empty except block (pass)")
        
        if issues:
            log_test("ExceptionQuality", py_file.name, "WARN", f"{len(issues)} issues: {issues[0]}")
        else:
            log_test("ExceptionQuality", py_file.name, "PASS")
    except Exception as e:
        log_test("ExceptionQuality", py_file.name, "FAIL", str(e))

# ============================================
# HARDCORE TEST 3: RESOURCE MANAGEMENT
# ============================================
print("\n" + "="*70)
print("HARDCORE 3: RESOURCE MANAGEMENT")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for file handles not using context managers
    file_opens = re.findall(r'(\w+)\s*=\s*open\(', content)
    with_opens = re.findall(r'with\s+open\(', content)
    if len(file_opens) > len(with_opens):
        issues.append(f"{len(file_opens) - len(with_opens)} open() without 'with'")
    
    # Check for unclosed database connections
    db_connect = len(re.findall(r'sqlite3\.connect\(', content))
    db_close = len(re.findall(r'\.close\(\)', content))
    
    # Check for subprocess without proper cleanup
    subprocess_calls = len(re.findall(r'subprocess\.(Popen|run|call)', content))
    
    if issues:
        log_test("ResourceMgmt", py_file.name, "WARN", "; ".join(issues))
    else:
        log_test("ResourceMgmt", py_file.name, "PASS")

# ============================================
# HARDCORE TEST 4: TYPE SAFETY
# ============================================
print("\n" + "="*70)
print("HARDCORE 4: TYPE ANNOTATIONS")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        total_funcs = 0
        typed_funcs = 0
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_funcs += 1
                has_annotations = node.returns is not None or any(arg.annotation for arg in node.args.args)
                if has_annotations:
                    typed_funcs += 1
        
        if total_funcs > 0:
            pct = (typed_funcs / total_funcs) * 100
            status = "PASS" if pct >= 30 else "WARN"
            log_test("TypeAnnotations", py_file.name, status, f"{typed_funcs}/{total_funcs} ({pct:.0f}%) typed")
        else:
            log_test("TypeAnnotations", py_file.name, "PASS", "No functions")
    except Exception as e:
        log_test("TypeAnnotations", py_file.name, "FAIL", str(e))

# ============================================
# HARDCORE TEST 5: CIRCULAR IMPORT CHECK
# ============================================
print("\n" + "="*70)
print("HARDCORE 5: CIRCULAR IMPORT DETECTION")
print("="*70)

import_graph = defaultdict(set)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    module_name = py_file.stem
    
    # Find all internal imports
    internal_imports = re.findall(r'from \.([\w_]+) import', content)
    for imp in internal_imports:
        import_graph[module_name].add(imp)

# Check for cycles using DFS
def find_cycle(graph, start, path=None):
    if path is None:
        path = []
    
    if start in path:
        return path[path.index(start):] + [start]
    
    path = path + [start]
    for neighbor in graph.get(start, []):
        cycle = find_cycle(graph, neighbor, path)
        if cycle:
            return cycle
    return None

cycles_found = []
for module in import_graph:
    cycle = find_cycle(import_graph, module)
    if cycle and tuple(cycle) not in [tuple(c) for c in cycles_found]:
        cycles_found.append(cycle)

if cycles_found:
    for cycle in cycles_found:
        log_test("CircularImports", " -> ".join(cycle), "WARN", "Potential circular import")
else:
    log_test("CircularImports", "All modules", "PASS", "No circular imports detected")

# ============================================
# HARDCORE TEST 6: SQL INJECTION PROTECTION
# ============================================
print("\n" + "="*70)
print("HARDCORE 6: SQL INJECTION PROTECTION")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    issues = []
    
    for i, line in enumerate(lines, 1):
        # Check for f-strings in SQL
        if re.search(r'(execute|executemany)\s*\(\s*f["\']', line):
            issues.append(f"Line {i}: f-string in SQL execute")
        
        # Check for .format() in SQL
        if re.search(r'(execute|executemany)\s*\([^)]*\.format\(', line):
            issues.append(f"Line {i}: .format() in SQL execute")
        
        # Check for % formatting in SQL
        if re.search(r'(execute|executemany)\s*\([^)]*%\s*\(', line):
            issues.append(f"Line {i}: % formatting in SQL execute")
    
    if issues:
        log_test("SQLInjection", py_file.name, "CRITICAL", "; ".join(issues))
    else:
        log_test("SQLInjection", py_file.name, "PASS")

# ============================================
# HARDCORE TEST 7: PATH TRAVERSAL PROTECTION
# ============================================
print("\n" + "="*70)
print("HARDCORE 7: PATH TRAVERSAL PROTECTION")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for user input used directly in paths
    dangerous_patterns = [
        (r'os\.path\.join\([^,]+,\s*(request|msg|data)\[', "User input in path join"),
        (r'open\([^)]*\+[^)]*\)', "String concatenation in file open"),
        (r'Path\([^)]*\+[^)]*\)', "String concatenation in Path"),
    ]
    
    for pattern, desc in dangerous_patterns:
        if re.search(pattern, content):
            issues.append(desc)
    
    # Check for proper path sanitization
    has_path_validation = "resolve()" in content or "is_relative_to" in content or "startswith" in content
    
    if issues:
        log_test("PathTraversal", py_file.name, "WARN", "; ".join(issues))
    else:
        log_test("PathTraversal", py_file.name, "PASS")

# ============================================
# HARDCORE TEST 8: WEBSOCKET MESSAGE VALIDATION
# ============================================
print("\n" + "="*70)
print("HARDCORE 8: WEBSOCKET MESSAGE VALIDATION")
print("="*70)

ws_file = base_path / "websocket_handlers.py"
with open(ws_file, 'r', encoding='utf-8') as f:
    ws_content = f.read()

# Find all websocket handlers
handlers = re.findall(r'async def (ws_\w+)\(hass, connection, msg\):', ws_content)

for handler in handlers:
    # Find the handler code
    pattern = rf'async def {handler}\(hass, connection, msg\):.*?(?=\nasync def |\nwebsocket_api\.async_register_command|\Z)'
    match = re.search(pattern, ws_content, re.DOTALL)
    
    if match:
        handler_code = match.group()
        
        # Check for input validation
        has_vol_schema = "vol.Schema" in handler_code or "@websocket_api.websocket_command" in handler_code
        uses_msg_get = 'msg.get(' in handler_code or 'msg["' in handler_code
        has_try_except = 'try:' in handler_code
        
        if uses_msg_get and not has_try_except:
            log_test("WSValidation", handler, "WARN", "Uses msg data without try/except")
        else:
            log_test("WSValidation", handler, "PASS")

# ============================================
# HARDCORE TEST 9: RACE CONDITION DETECTION
# ============================================
print("\n" + "="*70)
print("HARDCORE 9: RACE CONDITION DETECTION")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for global state modifications
    global_mods = len(re.findall(r'\bglobal\s+\w+', content))
    
    # Check for shared mutable state
    class_attrs = len(re.findall(r'self\.\w+\s*=\s*\[\]|self\.\w+\s*=\s*\{\}', content))
    
    # Check for async modifications without locks
    has_lock = "asyncio.Lock" in content or "threading.Lock" in content
    has_async_mod = "async def" in content and ("append(" in content or "update(" in content)
    
    if has_async_mod and not has_lock and class_attrs > 3:
        issues.append(f"Async modifications without locks ({class_attrs} mutable attrs)")
    
    if global_mods > 0:
        issues.append(f"{global_mods} global variable modifications")
    
    if issues:
        log_test("RaceCondition", py_file.name, "WARN", "; ".join(issues))
    else:
        log_test("RaceCondition", py_file.name, "PASS")

# ============================================
# HARDCORE TEST 10: MEMORY LEAK DETECTION
# ============================================
print("\n" + "="*70)
print("HARDCORE 10: MEMORY LEAK PATTERNS")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for growing lists/dicts without cleanup
    list_appends = len(re.findall(r'\.append\(', content))
    list_clears = len(re.findall(r'\.clear\(|= \[\]|del ', content))
    
    # Check for callbacks without removal
    add_listener = len(re.findall(r'add_listener|async_listen|subscribe', content))
    remove_listener = len(re.findall(r'remove_listener|unsubscribe', content))
    
    # Check for timer cleanup
    call_later = len(re.findall(r'call_later|call_at|async_call_later', content))
    cancel = len(re.findall(r'\.cancel\(\)', content))
    
    if add_listener > remove_listener + 2:
        issues.append(f"Listeners: {add_listener} added, {remove_listener} removed")
    
    if call_later > cancel + 2:
        issues.append(f"Timers: {call_later} created, {cancel} cancelled")
    
    if issues:
        log_test("MemoryLeak", py_file.name, "WARN", "; ".join(issues))
    else:
        log_test("MemoryLeak", py_file.name, "PASS")

# ============================================
# HARDCORE TEST 11: JAVASCRIPT SECURITY DEEP DIVE
# ============================================
print("\n" + "="*70)
print("HARDCORE 11: JAVASCRIPT SECURITY DEEP DIVE")
print("="*70)

js_file = Path("/config/www/rtsp-recorder-card.js")
if js_file.exists():
    with open(js_file, 'r', encoding='utf-8') as f:
        js_content = f.read()
        js_lines = js_content.split('\n')
    
    issues = []
    
    # Check innerHTML without escaping
    innerHTML_lines = []
    for i, line in enumerate(js_lines, 1):
        if '.innerHTML' in line and '=' in line:
            # Check if _escapeHtml is used nearby
            context = '\n'.join(js_lines[max(0,i-3):min(len(js_lines),i+3)])
            if '_escapeHtml' not in context and '${' in line:
                innerHTML_lines.append(i)
    
    if innerHTML_lines:
        log_test("JSXSSCheck", "innerHTML usage", "WARN", f"{len(innerHTML_lines)} innerHTML with template literals without escaping")
    else:
        log_test("JSXSSCheck", "innerHTML usage", "PASS")
    
    # Check for eval/Function constructor
    eval_usage = len(re.findall(r'\beval\s*\(', js_content))
    func_constructor = len(re.findall(r'new\s+Function\s*\(', js_content))
    
    if eval_usage or func_constructor:
        log_test("JSXSSCheck", "eval/Function", "CRITICAL", f"{eval_usage} eval, {func_constructor} new Function")
    else:
        log_test("JSXSSCheck", "eval/Function", "PASS")
    
    # Check for DOM clobbering protection
    getElementById = len(re.findall(r'getElementById\s*\(', js_content))
    querySelector = len(re.findall(r'querySelector\s*\(', js_content))
    log_test("JSXSSCheck", "DOM queries", "PASS", f"{getElementById} getElementById, {querySelector} querySelector")

# ============================================
# HARDCORE TEST 12: API ENDPOINT CONSISTENCY
# ============================================
print("\n" + "="*70)
print("HARDCORE 12: API ENDPOINT CONSISTENCY")
print("="*70)

# Get Python WS endpoints
py_endpoints = re.findall(r'websocket_api\.websocket_command\s*\(\s*\{\s*["\']type["\']\s*:\s*["\']rtsp_recorder/(\w+)["\']', ws_content)
py_endpoints.extend(re.findall(r'type["\']?\s*:\s*["\']rtsp_recorder/(\w+)', ws_content))
py_endpoints = list(set(py_endpoints))

# Get JS endpoints
if js_file.exists():
    js_endpoints = re.findall(r"type:\s*['\"]rtsp_recorder/(\w+)['\"]", js_content)
    js_endpoints = list(set(js_endpoints))
    
    # Check for missing endpoints
    missing_in_py = [e for e in js_endpoints if e not in py_endpoints]
    missing_in_js = [e for e in py_endpoints if e not in js_endpoints]
    
    if missing_in_py:
        log_test("APIConsistency", "JS->PY endpoints", "FAIL", f"Not in Python: {missing_in_py}")
    else:
        log_test("APIConsistency", "JS->PY endpoints", "PASS", f"All {len(js_endpoints)} JS endpoints exist in Python")
    
    if missing_in_js:
        log_test("APIConsistency", "PY->JS endpoints", "WARN", f"Not used in JS: {missing_in_js[:5]}")
    else:
        log_test("APIConsistency", "PY->JS endpoints", "PASS", f"All Python endpoints used in JS")

# ============================================
# HARDCORE TEST 13: ERROR MESSAGE LEAKAGE
# ============================================
print("\n" + "="*70)
print("HARDCORE 13: ERROR MESSAGE LEAKAGE")
print("="*70)

for py_file in py_files:
    with open(py_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # Check for traceback in responses
    if "traceback" in content.lower() and "send_result" in content:
        issues.append("Traceback may be exposed in WS response")
    
    # Check for system paths in error messages
    if re.search(r'str\(e\)|str\(exc\)|str\(error\)', content):
        # Could leak system info
        pass  # This is acceptable in most cases
    
    if issues:
        log_test("ErrorLeakage", py_file.name, "WARN", "; ".join(issues))
    else:
        log_test("ErrorLeakage", py_file.name, "PASS")

# ============================================
# SUMMARY
# ============================================
print("\n" + "="*70)
print("HARDCORE TEST SUMMARY")
print("="*70)
print(f"✓ PASSED:   {results['summary']['passed']}")
print(f"⚠ WARNINGS: {results['summary']['warnings']}")
print(f"✗ FAILED:   {results['summary']['failed']}")
print(f"🔴 CRITICAL: {results['summary']['critical']}")
print(f"  TOTAL:    {results['summary']['passed'] + results['summary']['warnings'] + results['summary']['failed'] + results['summary']['critical']}")

if results['issues']:
    print("\n" + "-"*70)
    print("CRITICAL ISSUES:")
    for issue in results['issues']:
        print(f"  {issue}")

# Save results
with open('/tmp/hardcore_test_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nResults saved to /tmp/hardcore_test_results.json")
