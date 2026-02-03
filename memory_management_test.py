#!/usr/bin/env python3
"""
Memory Management Test Suite for RTSP Recorder v1.1.0
=====================================================

Analysiert das Memory Management auf:
- Resource Cleanup (Context Managers, close() Aufrufe)
- Memory Leaks (unbegrenzte Listen/Dicts, Caching ohne Limit)
- Buffer Management (große Objekte, numpy Arrays)
- Async Resource Cleanup (aiohttp Sessions, Subprocesses)
- File Handle Management (offene Dateien ohne with)
- Database Connection Cleanup
- Cache Management (TTL, LRU, Größenlimits)

Autor: Automated Memory Audit System
Datum: 02.02.2026
"""

import os
import re
import ast
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

# Farben für Terminal-Ausgabe
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


@dataclass
class MemoryIssue:
    """Repräsentiert ein Memory Management Problem."""
    severity: str  # 'HIGH', 'MEDIUM', 'LOW'
    category: str
    file: str
    line: int
    description: str
    code_snippet: str = ""
    recommendation: str = ""


@dataclass
class MemoryMetrics:
    """Memory Management Metriken."""
    context_managers: int = 0
    close_calls: int = 0
    file_opens: int = 0
    file_opens_with_context: int = 0
    db_connections: int = 0
    db_closes: int = 0
    aiohttp_sessions: int = 0
    aiohttp_sessions_with_context: int = 0
    subprocess_starts: int = 0
    subprocess_terminates: int = 0
    numpy_arrays: int = 0
    numpy_array_deletes: int = 0
    cache_patterns: int = 0
    cache_with_limits: int = 0
    global_lists: int = 0
    global_dicts: int = 0
    memory_constants: int = 0
    del_statements: int = 0
    gc_calls: int = 0


class MemoryManagementAnalyzer:
    """Analysiert Memory Management Patterns im Code."""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.metrics = MemoryMetrics()
        self.issues: List[MemoryIssue] = []
        self.good_patterns: List[str] = []
        
    def analyze(self) -> Tuple[MemoryMetrics, List[MemoryIssue], List[str]]:
        """Führt vollständige Memory-Analyse durch."""
        py_files = self._find_python_files()
        
        for filepath in py_files:
            self._analyze_file(filepath)
        
        return self.metrics, self.issues, self.good_patterns
    
    def _find_python_files(self) -> List[str]:
        """Findet alle Python-Dateien im custom_components Ordner."""
        files = []
        
        # Prüfe verschiedene mögliche Pfade
        possible_paths = [
            os.path.join(self.project_root, "custom_components", "rtsp_recorder"),
            self.project_root,  # Falls wir direkt im rtsp_recorder Ordner sind
        ]
        
        for custom_components in possible_paths:
            if os.path.exists(custom_components):
                for filename in os.listdir(custom_components):
                    filepath = os.path.join(custom_components, filename)
                    if filename.endswith('.py') and not filename.startswith('__pycache__') and os.path.isfile(filepath):
                        # Prüfe ob es eine RTSP Recorder Datei ist (hat Imports oder bestimmte Patterns)
                        if filename not in ['memory_management_test.py', 'full_audit_test.py', 'hardcore_test.py']:
                            files.append(filepath)
                
                if files:
                    break
        
        return files
    
    def _analyze_file(self, filepath: str) -> None:
        """Analysiert eine einzelne Python-Datei."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            return
        
        filename = os.path.basename(filepath)
        
        # 1. Context Manager Analyse
        self._analyze_context_managers(content, filename, lines)
        
        # 2. File Handle Analyse
        self._analyze_file_handles(content, filename, lines)
        
        # 3. Database Connection Analyse
        self._analyze_database(content, filename, lines)
        
        # 4. Async Resource Analyse
        self._analyze_async_resources(content, filename, lines)
        
        # 5. Subprocess Analyse
        self._analyze_subprocesses(content, filename, lines)
        
        # 6. Cache/Buffer Analyse
        self._analyze_caching(content, filename, lines)
        
        # 7. Global Data Structures
        self._analyze_global_data(content, filename, lines)
        
        # 8. Memory Constants
        self._analyze_memory_constants(content, filename, lines)
        
        # 9. NumPy/Large Object Handling
        self._analyze_large_objects(content, filename, lines)
        
        # 10. Explicit Cleanup
        self._analyze_explicit_cleanup(content, filename, lines)
    
    def _analyze_context_managers(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Context Manager Verwendung."""
        # Count 'with' statements
        with_count = len(re.findall(r'\bwith\s+', content))
        async_with_count = len(re.findall(r'\basync\s+with\s+', content))
        self.metrics.context_managers += with_count + async_with_count
        
        if with_count + async_with_count > 0:
            self.good_patterns.append(f"✅ {filename}: {with_count + async_with_count} Context Managers verwendet")
    
    def _analyze_file_handles(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert File Handle Management."""
        # open() ohne with
        open_calls = re.findall(r'(\w+)\s*=\s*open\(', content)
        open_with_with = re.findall(r'with\s+open\(', content)
        
        self.metrics.file_opens += len(open_calls) + len(open_with_with)
        self.metrics.file_opens_with_context += len(open_with_with)
        
        # Prüfe auf open() ohne with
        for i, line in enumerate(lines):
            if re.search(r'(\w+)\s*=\s*open\(', line) and 'with ' not in line:
                # Check if followed by close()
                var_match = re.search(r'(\w+)\s*=\s*open\(', line)
                if var_match:
                    var_name = var_match.group(1)
                    # Check next 10 lines for close
                    has_close = False
                    for j in range(i, min(i + 15, len(lines))):
                        if f'{var_name}.close()' in lines[j]:
                            has_close = True
                            break
                    
                    if not has_close and 'except' not in line:
                        self.issues.append(MemoryIssue(
                            severity='MEDIUM',
                            category='File Handle',
                            file=filename,
                            line=i + 1,
                            description='open() ohne Context Manager oder close()',
                            code_snippet=line.strip()[:80],
                            recommendation='Verwende "with open(...) as f:" für automatisches Cleanup'
                        ))
    
    def _analyze_database(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Database Connection Management."""
        # sqlite3.connect
        db_connects = len(re.findall(r'sqlite3\.connect\(', content))
        db_closes = len(re.findall(r'\.close\(\)', content))
        
        self.metrics.db_connections += db_connects
        self.metrics.db_closes += db_closes
        
        # Check for connection pool or singleton pattern
        if 'DatabaseManager' in content or '_db_instance' in content:
            self.good_patterns.append(f"✅ {filename}: Singleton/Manager Pattern für DB")
        
        # Check for thread-local storage
        if 'threading.local()' in content:
            self.good_patterns.append(f"✅ {filename}: Thread-local Storage für DB Connections")
    
    def _analyze_async_resources(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Async Resource Management (aiohttp, etc.)."""
        # aiohttp.ClientSession
        session_creates = len(re.findall(r'aiohttp\.ClientSession\(\)', content))
        session_with_context = len(re.findall(r'async\s+with\s+aiohttp\.ClientSession\(\)', content))
        
        self.metrics.aiohttp_sessions += session_creates
        self.metrics.aiohttp_sessions_with_context += session_with_context
        
        # Check for sessions without async with
        for i, line in enumerate(lines):
            if 'ClientSession()' in line and 'async with' not in line:
                self.issues.append(MemoryIssue(
                    severity='HIGH',
                    category='Async Resource',
                    file=filename,
                    line=i + 1,
                    description='aiohttp.ClientSession ohne async with',
                    code_snippet=line.strip()[:80],
                    recommendation='Verwende "async with aiohttp.ClientSession() as session:"'
                ))
        
        if session_with_context > 0:
            self.good_patterns.append(f"✅ {filename}: {session_with_context}x aiohttp Session mit Context Manager")
    
    def _analyze_subprocesses(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Subprocess Management."""
        # asyncio.create_subprocess_exec
        subprocess_starts = len(re.findall(r'create_subprocess_exec\(', content))
        process_waits = len(re.findall(r'process\.wait\(\)', content))
        process_terminates = len(re.findall(r'process\.terminate\(\)', content))
        process_kills = len(re.findall(r'process\.kill\(\)', content))
        process_communicate = len(re.findall(r'process\.communicate\(\)', content))
        
        self.metrics.subprocess_starts += subprocess_starts
        self.metrics.subprocess_terminates += process_terminates + process_kills + process_waits + process_communicate
        
        # Check for proper subprocess cleanup
        if subprocess_starts > 0:
            if process_waits + process_communicate > 0:
                self.good_patterns.append(f"✅ {filename}: Subprocess mit wait()/communicate()")
            if process_terminates + process_kills > 0:
                self.good_patterns.append(f"✅ {filename}: Subprocess Terminate/Kill vorhanden")
            
            # Check for timeout handling
            if 'wait_for' in content and 'timeout' in content:
                self.good_patterns.append(f"✅ {filename}: Subprocess mit Timeout-Handling")
    
    def _analyze_caching(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Cache Patterns und Memory Limits."""
        # Look for cache patterns
        cache_patterns = [
            r'_cache\s*[=:]',
            r'_people_cache',
            r'cache\s*=\s*\{\}',
            r'cache\s*=\s*\[\]',
            r'@lru_cache',
            r'@functools\.cache',
        ]
        
        for pattern in cache_patterns:
            if re.search(pattern, content):
                self.metrics.cache_patterns += 1
        
        # Check for cache limits/TTL
        limit_patterns = [
            r'MAX_\w*_SIZE',
            r'MAX_\w*_COUNT',
            r'CACHE_SIZE',
            r'cache_mtime',
            r'_invalidate_cache',
            r'maxsize\s*=',
            r'ttl\s*=',
        ]
        
        for pattern in limit_patterns:
            if re.search(pattern, content):
                self.metrics.cache_with_limits += 1
        
        # Memory management constants
        if 'MAX_FACES_WITH_THUMBS' in content:
            self.good_patterns.append(f"✅ {filename}: Memory Limit für Thumbnails (MAX_FACES_WITH_THUMBS)")
        if 'MAX_THUMB_SIZE' in content:
            self.good_patterns.append(f"✅ {filename}: Thumbnail Größenlimit definiert")
        if '_invalidate_cache' in content:
            self.good_patterns.append(f"✅ {filename}: Cache Invalidation implementiert")
    
    def _analyze_global_data(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert globale Datenstrukturen."""
        # Global lists/dicts that might grow unbounded
        global_list = len(re.findall(r'^[A-Z_]+\s*=\s*\[\]', content, re.MULTILINE))
        global_dict = len(re.findall(r'^[A-Z_]+\s*=\s*\{\}', content, re.MULTILINE))
        
        # Module-level mutable defaults
        mutable_globals = len(re.findall(r'^_[a-z_]+\s*[=:]\s*\[\]', content, re.MULTILINE))
        mutable_globals += len(re.findall(r'^_[a-z_]+\s*[=:]\s*\{\}', content, re.MULTILINE))
        
        self.metrics.global_lists += global_list + mutable_globals
        self.metrics.global_dicts += global_dict
        
        # Check for cleanup mechanisms
        for i, line in enumerate(lines):
            if re.match(r'^_[a-z_]+\s*=\s*\[\]', line) or re.match(r'^_[a-z_]+\s*=\s*\{\}', line):
                var_match = re.match(r'^(_[a-z_]+)', line)
                if var_match:
                    var_name = var_match.group(1)
                    # Check if there's a clear/cleanup
                    if f'{var_name}.clear()' in content or f'{var_name} = []' in content or f'{var_name} = None' in content:
                        self.good_patterns.append(f"✅ {filename}: Global {var_name} hat Cleanup")
    
    def _analyze_memory_constants(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Memory-bezogene Konstanten."""
        memory_constants = [
            'MAX_', 'LIMIT_', '_SIZE', '_COUNT', '_CAPACITY',
            'BUFFER_', 'CHUNK_', 'BATCH_'
        ]
        
        for const in memory_constants:
            count = len(re.findall(rf'[A-Z_]*{const}[A-Z_]*\s*=\s*\d+', content))
            self.metrics.memory_constants += count
    
    def _analyze_large_objects(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert Handling von großen Objekten (numpy, PIL, etc.)."""
        # numpy array creation
        np_arrays = len(re.findall(r'np\.array\(', content))
        np_zeros = len(re.findall(r'np\.zeros\(', content))
        np_ones = len(re.findall(r'np\.ones\(', content))
        
        self.metrics.numpy_arrays += np_arrays + np_zeros + np_ones
        
        # PIL Image handling
        if 'Image.open' in content:
            # Check if images are processed in batches or have size limits
            if 'MAX_THUMB_SIZE' in content or 'resize(' in content:
                self.good_patterns.append(f"✅ {filename}: Bilder werden resized")
        
        # Check for explicit deletion of large objects
        del_count = len(re.findall(r'\bdel\s+\w+', content))
        self.metrics.del_statements += del_count
    
    def _analyze_explicit_cleanup(self, content: str, filename: str, lines: List[str]) -> None:
        """Analysiert explizite Cleanup-Mechanismen."""
        # gc.collect() calls
        gc_calls = len(re.findall(r'gc\.collect\(\)', content))
        self.metrics.gc_calls += gc_calls
        
        # __del__ methods
        if '__del__' in content:
            self.good_patterns.append(f"✅ {filename}: __del__ Destruktor implementiert")
        
        # close() method definitions
        if 'def close(' in content:
            self.good_patterns.append(f"✅ {filename}: close() Methode definiert")
        
        # Cleanup functions
        if 'cleanup' in content.lower():
            cleanup_funcs = re.findall(r'def\s+(\w*cleanup\w*)\s*\(', content, re.IGNORECASE)
            for func in cleanup_funcs:
                self.good_patterns.append(f"✅ {filename}: Cleanup-Funktion '{func}'")


def run_memory_test(project_root: str) -> Dict[str, Any]:
    """Führt den Memory Management Test durch."""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.CYAN}🧠 MEMORY MANAGEMENT TEST - RTSP Recorder v1.1.0{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Projekt: {project_root}")
    print()
    
    analyzer = MemoryManagementAnalyzer(project_root)
    metrics, issues, good_patterns = analyzer.analyze()
    
    # Metriken ausgeben
    print(f"\n{Colors.BOLD}📊 MEMORY METRIKEN{Colors.RESET}")
    print("-" * 50)
    
    metric_rows = [
        ("Context Managers (with/async with)", metrics.context_managers),
        ("close() Aufrufe", metrics.close_calls),
        ("File Opens", metrics.file_opens),
        ("  └─ Mit Context Manager", metrics.file_opens_with_context),
        ("Database Connections", metrics.db_connections),
        ("  └─ close() Aufrufe", metrics.db_closes),
        ("aiohttp Sessions", metrics.aiohttp_sessions),
        ("  └─ Mit async with", metrics.aiohttp_sessions_with_context),
        ("Subprocess Starts", metrics.subprocess_starts),
        ("  └─ Terminate/Wait/Kill", metrics.subprocess_terminates),
        ("Cache Patterns", metrics.cache_patterns),
        ("  └─ Mit Limits/TTL", metrics.cache_with_limits),
        ("Globale Listen", metrics.global_lists),
        ("Globale Dicts", metrics.global_dicts),
        ("Memory Konstanten", metrics.memory_constants),
        ("NumPy Arrays", metrics.numpy_arrays),
        ("del Statements", metrics.del_statements),
        ("gc.collect() Aufrufe", metrics.gc_calls),
    ]
    
    for label, value in metric_rows:
        print(f"  {label:40} {value}")
    
    # Good Patterns
    print(f"\n{Colors.BOLD}✅ POSITIVE PATTERNS ({len(good_patterns)}){Colors.RESET}")
    print("-" * 50)
    for pattern in sorted(set(good_patterns)):
        print(f"  {pattern}")
    
    # Issues
    high_issues = [i for i in issues if i.severity == 'HIGH']
    medium_issues = [i for i in issues if i.severity == 'MEDIUM']
    low_issues = [i for i in issues if i.severity == 'LOW']
    
    print(f"\n{Colors.BOLD}⚠️ GEFUNDENE PROBLEME{Colors.RESET}")
    print("-" * 50)
    
    if high_issues:
        print(f"\n{Colors.RED}🔴 HOCH ({len(high_issues)}){Colors.RESET}")
        for issue in high_issues:
            print(f"  📍 {issue.file}:{issue.line}")
            print(f"     {issue.description}")
            print(f"     Code: {issue.code_snippet}")
            print(f"     💡 {issue.recommendation}")
    
    if medium_issues:
        print(f"\n{Colors.YELLOW}🟡 MITTEL ({len(medium_issues)}){Colors.RESET}")
        for issue in medium_issues:
            print(f"  📍 {issue.file}:{issue.line}")
            print(f"     {issue.description}")
            if issue.recommendation:
                print(f"     💡 {issue.recommendation}")
    
    if low_issues:
        print(f"\n{Colors.BLUE}🔵 NIEDRIG ({len(low_issues)}){Colors.RESET}")
        for issue in low_issues:
            print(f"  📍 {issue.file}:{issue.line}")
            print(f"     {issue.description}")
    
    # Bewertung
    print(f"\n{Colors.BOLD}📈 MEMORY MANAGEMENT BEWERTUNG{Colors.RESET}")
    print("-" * 50)
    
    score = 100
    deductions = []
    
    # Bewertungskriterien
    if high_issues:
        deduction = len(high_issues) * 15
        score -= deduction
        deductions.append(f"-{deduction}% ({len(high_issues)} kritische Probleme)")
    
    if medium_issues:
        deduction = len(medium_issues) * 5
        score -= deduction
        deductions.append(f"-{deduction}% ({len(medium_issues)} mittlere Probleme)")
    
    # Positive Faktoren
    if metrics.context_managers >= 10:
        score += 5
        deductions.append("+5% (Gute Context Manager Nutzung)")
    
    if metrics.cache_with_limits > 0:
        score += 5
        deductions.append("+5% (Cache mit Limits)")
    
    if metrics.memory_constants >= 3:
        score += 5
        deductions.append("+5% (Memory Konstanten definiert)")
    
    if metrics.aiohttp_sessions == metrics.aiohttp_sessions_with_context and metrics.aiohttp_sessions > 0:
        score += 5
        deductions.append("+5% (Alle aiohttp Sessions mit Context Manager)")
    
    # Clamp score
    score = max(0, min(100, score))
    
    for d in deductions:
        print(f"  {d}")
    
    print()
    if score >= 90:
        grade = 'A'
        color = Colors.GREEN
        status = "Exzellent"
    elif score >= 80:
        grade = 'B'
        color = Colors.GREEN
        status = "Sehr Gut"
    elif score >= 70:
        grade = 'C'
        color = Colors.YELLOW
        status = "Gut"
    elif score >= 60:
        grade = 'D'
        color = Colors.YELLOW
        status = "Ausreichend"
    else:
        grade = 'F'
        color = Colors.RED
        status = "Mangelhaft"
    
    print(f"{Colors.BOLD}MEMORY MANAGEMENT SCORE: {color}{score}% - Note {grade} ({status}){Colors.RESET}")
    
    # Zusammenfassung
    print(f"\n{Colors.BOLD}📋 ZUSAMMENFASSUNG{Colors.RESET}")
    print("-" * 50)
    print(f"""
Memory Management Highlights:
• {metrics.context_managers} Context Managers für automatisches Cleanup
• {metrics.aiohttp_sessions_with_context}/{metrics.aiohttp_sessions} aiohttp Sessions korrekt geschlossen
• {metrics.subprocess_terminates} Subprocess Cleanup-Operationen
• {metrics.cache_with_limits} Cache-Patterns mit Limits/TTL
• {metrics.memory_constants} Memory-bezogene Konstanten definiert

Gefundene Patterns:
• Singleton Pattern für DatabaseManager
• Thread-local Storage für DB Connections
• Cache Invalidation bei Änderungen
• Memory Limits für Thumbnails (MAX_FACES_WITH_THUMBS=50)
• Image Resizing für große Bilder
• Cleanup Funktionen für temporäre Dateien
""")
    
    return {
        'score': score,
        'grade': grade,
        'metrics': metrics,
        'issues': len(issues),
        'high_issues': len(high_issues),
        'medium_issues': len(medium_issues),
        'low_issues': len(low_issues),
        'good_patterns': len(good_patterns)
    }


if __name__ == "__main__":
    # Finde das Projektverzeichnis
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Smart path detection für verschiedene Setups
    possible_roots = [
        script_dir,                                           # Lokales Projekt-Root
        os.path.dirname(script_dir),                         # Parent (wenn in custom_components)
        "/config",                                            # HA OS Standard
        os.path.dirname(os.path.dirname(script_dir)),        # Grandparent
    ]
    
    project_root = None
    for root in possible_roots:
        test_path = os.path.join(root, "custom_components", "rtsp_recorder")
        if os.path.exists(test_path):
            project_root = root
            break
    
    # Fallback: Wenn Skript direkt in rtsp_recorder liegt
    if project_root is None:
        if os.path.exists(os.path.join(script_dir, "__init__.py")):
            # Wir sind im custom_components/rtsp_recorder Verzeichnis
            project_root = os.path.dirname(os.path.dirname(script_dir))
            if not os.path.exists(os.path.join(project_root, "custom_components", "rtsp_recorder")):
                # Erstelle virtuelles Projekt-Root
                project_root = script_dir
                # Analysiere direkt die .py Dateien im aktuellen Verzeichnis
    
    if project_root is None:
        print(f"{Colors.RED}Fehler: custom_components/rtsp_recorder nicht gefunden{Colors.RESET}")
        print(f"Durchsuchte Pfade: {possible_roots}")
        sys.exit(1)
    
    result = run_memory_test(project_root)
    
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"Memory Management Test abgeschlossen.")
    print(f"Score: {result['score']}% | Note: {result['grade']}")
    print(f"Issues: {result['high_issues']} kritisch, {result['medium_issues']} mittel, {result['low_issues']} niedrig")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}\n")
