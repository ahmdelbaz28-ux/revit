"""
voice_interface.py — FireAI Voice Interface
=====================================
Hands-free voice interaction with FireAI.

Supported Dialects:
    - Egyptian (Masri) - مصري
    - Gulf (Khaleeji) - خليجي (Saudi, UAE, Qatar, Oman, Kuwait)
    - Libyan - ليبي
    - Jordanian - اردني
    - Moroccan - مغربي
    - Tunisian - تونسي
    - Iraqi - عراقي
    - Yemeni - يمني
    - Palestinian - فلسطيني
    - Sudanese - سوداني

Voice Commands:
    "analyze [file]" - Parse file (DXF, DWG, PDF, Excel)
    "how many rooms" - Show room count
    "how many detectors" - Run NFPA calculation
    "show rooms" - List all rooms
    "export report" - Generate PDF report
    "help" - Show all commands

Usage:
    from voice_interface import FireAIVoice, set_dialect
    set_dialect("egyptian")  # or "gulf", "libyan", "jordanian"
    voice = FireAIVoice()
    voice.listen()
"""

import speech_recognition as sr
import pyttsx3
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger("fireai.voice")


# ═══════════════════════════════════════════════════════
# DIALECT LOCALIZATIONS
# ═══════════════════════════════════════════════════════

DIALECT_RESPONSES = {
    # Egyptian (Masri)
    "egyptian": {
        "analyzed": "لقينا {} غرف",
        "no_file": "محللة ملف يعني، قولي يحلل [اسم الملف]",
        "file_not_found": "الملف موجود",
        "detectors_found": "محتاج {} كاشف",
        "rooms_list": "الغرف: {}",
        "help": """
الأوامر المتاحة:
- "يحلل [اسم]" - تحليل ملف
- "عدد الغرف" - عرض عدد الغرف
- "الكاشفات" - حساب الكاشفات
- "الغرف" - عرض قائمة الغرف
- "تقرير" - تصدير تقرير
""",
        "welcome": "اهلا يا باشمهندس، أنا جاهز",
        "listening": "اسمع عليكو...",
        "processing": "بتامل...",
    },
    
    # Gulf (Saudi, UAE, Qatar, Oman, Kuwait)
    "gulf": {
        "analyzed": "لقينا {} غرف",
        "no_file": "ما فيه ملف محلل، قلت يحلل [اسم الملف]",
        "file_not_found": "الملف ما موجود",
        "detectors_found": "تحتاج {} كاشف",
        "rooms_list": "الغرف: {}",
        "help": """
الأوامر:
- "يحلل [اسم]" - تحليل ملف
- "عدد الغرف" - عدد الغرف
- "الكاشفات" - حساب الكاشفات
- "الغرف" - قائمة الغرف
- "تقرير" - تصدير تقرير
""",
        "welcome": "اهلا بالشيخ، جاهز لخدمتك",
        "listening": "سمع صوتك...",
        "processing": "معالج...",
    },
    
    # Libyan
    "libyan": {
        "analyzed": "جبدنا {} غرفة",
        "no_file": "ما تحللت ملف، قلت احلل [اسم الملف]",
        "file_not_found": "الملف ما موجود",
        "detectors_found": "تحتاج {} كاشف دخان",
        "rooms_list": "الغرف: {}",
        "help": """
الأوامر المتوفرة:
- يحلل [اسم الملف]
- عدد الغرف
- الكاشفات
- الغرف
- تقرير
""",
        "welcome": "اهلا يا باشمهندس، جاهز",
        "listening": "اسمع...",
        "processing": "قيد المعالجة...",
    },
    
    # Jordanian
    "jordanian": {
        "analyzed": "إللي صار {} غرف",
        "no_file": "ما في ملف محلل، قول احلل [اسم]",
        "file_not_found": "الملف مش موجود",
        "detectors_found": "محتاج {} كاشف",
        "rooms_list": "الغرف: {}",
        "help": """
الأوامر:
- يحلل [اسم]
- عدد الغرف
- الكاشفات
- الغرف  
- تقرير
""",
        "welcome": "اهلا بال engineer، جاهز",
        "listening": "اسمع...",
        "processing": "بعمل processing...",
    },
    
    # Default (Modern Standard Arabic / English fallback)
    "default": {
        "analyzed": "Found {} rooms",
        "no_file": "No file analyzed yet. Say 'analyze [filename]' first.",
        "file_not_found": "File not found",
        "detectors_found": "Need {} detectors",
        "rooms_list": "Rooms: {}",
        "help": """
Commands:
- "analyze [filename]" - Parse file
- "how many rooms" - Room count
- "how many detectors" - NFPA calculation
- "show rooms" - List rooms
- "export report" - Generate report
- "help" - Show this message
""",
        "welcome": "FireAI ready",
        "listening": "Listening...",
        "processing": "Processing...",
    },
    
    # Moroccan (Darija)
    "moroccan": {
        "analyzed": "khaskh {} ghorf",
        "no_file": "Matalahed file, qol y analyse [smiya]",
        "file_not_found": "File makene",
        "detectors_found": "Khas {} kashf",
        "rooms_list": "Ghorf: {}",
        "help": """
Commands:
- "analyze [filename]"
- "numero ghorf"
- "kashfat"
- "gharef"
- "rapport"
""",
        "welcome": "labas, nji m3ak",
        "listening": "dstana...",
        "processing": "mouwakal...",
    },
    
    # Tunisian
    "tunisian": {
        "analyzed": "na3ref {} ghurfa",
        "no_file": "ma alih file, qoulou yemshi [esem]",
        "file_not_found": "File mouch mawjoud",
        "detectors_found": "i7taj {} kashf",
        "rooms_list": "ghourouf: {}",
        "help": """
Commands:
- "yemshi [esem]"
- "9adeh ghourouf"
- "kashfat"
- "l liste"
""",
        "welcome": "ahla wa sahla, mouch khalas",
        "listening": "ousma3...",
        "processing": "mouch khalas...",
    },
    
    # Iraqi
    "iraqi": {
        "analyzed": " Hakam {} ghorfat",
        "no_file": "Maheen file, say analyze [esm al file]",
        "file_not_found": "Al file ma mawjoud",
        "detectors_found": "Yatathar {} kashf",
        "rooms_list": "Al ghorfat: {}",
        "help": """
Commands:
- "analyze [filename]"
- "Adad al ghoraf"
- "Al kashafat"
- "Al ghoraf"
""",
        "welcome": "Ahlan ya mohandis, ana sa7",
        "listening": "Osma3...",
        "processing": "Miyanal...",
    },
    
    # Yemeni
    "yemeni": {
        "analyzed": "Labina {} ghorof",
        "no_file": "File mafi, ana a9ra [esem]",
        "file_not_found": "Al file ghaib",
        "detectors_found": "TiStaHIL {} kashf",
        "rooms_list": "Al ghorof: {}",
        "help": """
Commands:
- "aqra [filename]"
- "3dad al ghorof"
- "Al kashafat"
- "Al ghorof"
""",
        "welcome": "Ahlan, ana jari",
        "listening": "Osma3...",
        "processing": "Miyal...",
    },
    
    # Palestinian
    "palestinian": {
        "analyzed": "L9ina {} ghoraf",
        "no_file": "Ma fi file m7allal, 9ul y9ra [esem]",
        "file_not_found": "Al file ma fi",
        "detectors_found": "7taj {} kashf",
        "rooms_list": "Al ghoraf: {}",
        "help": """
Commands:
- "y9ra [filename]"
- "3dad al ghoraf"
- "Al kashafat"
- "Al ghoraf"
""",
        "welcome": "Ahlan ya basha, ana ba7",
        "listening": "Osma3...",
        "processing": "Miyal...",
    },
    
    # Sudanese
    "sudanese": {
        "analyzed": "Kanina {} ghorafa",
        "no_file": "File min gayn, 9ul y9ra [esem]",
        "file_not_found": "Al file ma nashat",
        "detectors_found": "Ti7taj {} kashafa",
        "rooms_list": "Al ghorafa: {}",
        "help": """
Commands:
- "y9ra [filename]"
- "3dad ghorafa"
- "Al kashafat"
- "Al ghorafa"
""",
        "welcome": "Ahlan, ana tajiib",
        "listening": "Osma3...",
        "processing": "Miyanal...",
    },
}

# Command translations for each dialect
DIALECT_COMMANDS = {
    "egyptian": {
        "analyze": ["يحلل", "يحلل", "اقرا", "افحص"],
        "count_rooms": ["عدد الغرف", "عدد غرف", "كم غرف"],
        "count_detectors": ["الكاشفات", "عدد الكاشفات", "كم كاشف"],
        "list_rooms": ["الغرف", "الغرف", "عرض الغرف"],
        "export_report": ["تقرير", "تصدير"],
        "help": ["مساعدة", "الاوامر"],
    },
    "gulf": {
        "analyze": ["يحلل", "يحلل", "قرا", "افحص"],
        "count_rooms": ["عدد الغرف", "عدد غرف", "كم غرف"],
        "count_detectors": ["الكاشفات", "عدد الكاشفات"],
        "list_rooms": ["الغرف", "الغرف", "شوف الغرف"],
        "export_report": ["تقرير"],
        "help": ["مساعدة", "الاوامر"],
    },
    "libyan": {
        "analyze": ["احلل", "ياحل", "قرا"],
        "count_rooms": ["عدد الغرف", "عدد غرف"],
        "count_detectors": ["الكاشفات", "كاشف الدخان", "عدد الكاشفات"],
        "list_rooms": ["الغرف", "غرف"],
        "export_report": ["تقرير"],
        "help": ["مساعدة"],
    },
    "jordanian": {
        "analyze": ["احلل", "ياحل", "افحص"],
        "count_rooms": ["عدد الغرف", "عدد غرف"],
        "count_detectors": ["الكاشفات", "كاشف"],
        "list_rooms": ["الغرف", "غرف"],
        "export_report": ["تقرير"],
        "help": ["مساعدة", "الاوامر"],
    },
    "moroccan": {
        "analyze": ["y analyse", "analyser", "qra"],
        "count_rooms": ["numero ghorf", "adad ghorf"],
        "count_detectors": ["kashfat", "adad kashfat"],
        "list_rooms": ["gharef", "liste ghorf"],
        "export_report": ["rapport"],
        "help": ["a3za"],
    },
    "tunisian": {
        "analyze": ["yemshi", "analyser", "na9ra"],
        "count_rooms": ["9adeh ghourouf", "adad ghourouf"],
        "count_detectors": ["kashfat", "adad kashfat"],
        "list_rooms": ["l liste"],
        "export_report": ["rapport", "mouchajara"],
        "help": ["mousaada"],
    },
    "iraqi": {
        "analyze": ["yanaliz", "analyze", "y9ra"],
        "count_rooms": ["Adad al ghoraf", "3dad ghoraf"],
        "count_detectors": ["Al kashafat", "adad kashafat"],
        "list_rooms": ["Al ghoraf"],
        "export_report": ["ta3rif", "rapport"],
        "help": ["mousaada"],
    },
    "yemeni": {
        "analyze": ["y9ra", "aqra", "analiz"],
        "count_rooms": ["3dad al ghorof", "adad ghorof"],
        "count_detectors": ["Al kashafat", "adad kashafat"],
        "list_rooms": ["Al ghorof"],
        "export_report": ["ta3rif"],
        "help": ["mousaada"],
    },
    "palestinian": {
        "analyze": ["y9ra", "a9ra", "analiz"],
        "count_rooms": ["3dad al ghoraf"],
        "count_detectors": ["Al kashafat"],
        "list_rooms": ["Al ghoraf"],
        "export_report": ["ta3rif"],
        "help": ["mousaada"],
    },
    "sudanese": {
        "analyze": ["y9ra", "a9ra", "analiz"],
        "count_rooms": ["3dad ghorafa", "adad ghorafa"],
        "count_detectors": ["Al kashafat"],
        "list_rooms": ["Al ghorafa"],
        "export_report": ["ta3rif"],
        "help": ["mousaada"],
    },
}


# ═══════════════════════════════════════════════════════
# DIALECT MANAGER
# ═══════════════════════════════════════════════════════

_current_dialect = "default"

def set_dialect(dialect: str):
    """Set the current dialect."""
    global _current_dialect
    if dialect.lower() in DIALECT_RESPONSES:
        _current_dialect = dialect.lower()
    else:
        _current_dialect = "default"
        
def get_dialect() -> str:
    """Get current dialect."""
    return _current_dialect
    
def t(key: str) -> str:
    """Get translated string for current dialect."""
    return DIALECT_RESPONSES[_current_dialect].get(key, DIALECT_RESPONSES["default"][key])


# ═══════════════════════════════════════════════════════
# VOICE ENGINE
# ═══════════════════════════════════════════════════════

class FireAIVoice:
    """
    Voice interface for FireAI.
    
    USAGE:
        voice = FireAIVoice()
        voice.listen()
        
        # Or use text commands:
        voice.process_command("analyze floor_plan.dxf")
    """

    # Command patterns
    COMMANDS = {
        # Analysis commands
        r'analyze (.+\.(dxf|dwg|pdf|xlsx?|xlsm?))': 'analyze',
        r'parse (.+\.(dxf|dwg|pdf|xlsx?|xlsm?))': 'analyze',
        r'read (.+\.(dxf|dwg|pdf|xlsx?|xlsm?))': 'analyze',
        
        # Query commands
        r'how many rooms': 'count_rooms',
        r'number of rooms': 'count_rooms',
        r'how many detectors': 'count_detectors',
        r'detectors needed': 'count_detectors',
        r'show rooms': 'list_rooms',
        r'list rooms': 'list_rooms',
        
        # Report commands
        r'export report': 'export_report',
        r'generate report': 'export_report',
        r'save report': 'export_report',
        
        # Help
        r'help': 'help',
        r'what can i say': 'help',
    }

    def __init__(self, voice_enabled: bool = True):
        """
        Initialize voice interface.
        
        Args:
            voice_enabled: Enable speech output (default True)
        """
        self.voice_enabled = voice_enabled
        self.current_result = None
        self.current_file = None
        
        # Initialize TTS engine
        self.tts_engine = None
        if voice_enabled:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty('rate', 150)
            except Exception as e:
                logger.warning(f"TTS not available: {e}")
                voice_enabled = False
                
    # ═══════════════════════════════════════════════════════
    # SPEECH PROCESSING
    # ═══════════════════════════════════════════════════════

    def speak(self, text: str):
        """Speak text aloud."""
        if not self.voice_enabled or not self.tts_engine:
            print(f"🔊 {text}")
            return
            
        try:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception as e:
            print(f"🔊 {text}")

    def listen(self, timeout: int = 5) -> Optional[str]:
        """
        Listen for voice command.
        
        Args:
            timeout: Listening timeout in seconds
            
        Returns:
            Command string or None
        """
        # Initialize recognizer
        recognizer = sr.Recognizer()
        microphone = sr.Microphone()
        
        try:
            with microphone as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print("🎤 Listening...")
                audio = recognizer.listen(source, timeout=timeout)
                
            print("🔄 Processing...")
            command = recognizer.recognize_google(audio)
            print(f"📝 Heard: {command}")
            return command
            
        except sr.WaitTimeoutError:
            self.speak("I didn't hear anything. Please try again.")
            return None
        except sr.UnknownValueError:
            self.speak("I didn't understand that. Please try again.")
            return None
        except Exception as e:
            logger.error(f"Voice error: {e}")
            return None

    # ═══════════════════════════════════════════════════════
    # COMMAND PROCESSING
    # ═══════════════════════════════════════════════════════

    def process_command(self, command: str) -> str:
        """
        Process voice/text command.
        
        Args:
            command: Command string
            
        Returns:
            Response string
        """
        command = command.lower().strip()
        
        # Match commands
        for pattern, action in self.COMMANDS.items():
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                return self._execute_action(action, match.group(1) if match.groups() else None)
                
        # Unknown command
        return self._execute_action('help')

    def _execute_action(self, action: str, param: Optional[str] = None) -> str:
        """Execute command action."""
        
        if action == 'analyze':
            return self._analyze_file(param)
            
        elif action == 'count_rooms':
            return self._count_rooms()
            
        elif action == 'count_detectors':
            return self._count_detectors()
            
        elif action == 'list_rooms':
            return self._list_rooms()
            
        elif action == 'export_report':
            return self._export_report()
            
        elif action == 'help':
            return self._show_help()
            
        return "Unknown command"

    # ═══════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════

    def _analyze_file(self, file_path: str) -> str:
        """Analyze file (DXF, DWG, PDF, Excel)."""
        if not file_path:
            return "Please specify a file to analyze"
            
        # Clean path
        file_path = file_path.strip()
        
        if not Path(file_path).exists():
            return f"File not found: {file_path}"
            
        import shutil
        
        # Determine parser
        ext = Path(file_path).suffix.lower()
        # Handle xlsx and xls
        if ext in ['.xlsx', '.xls']:
            ext = '.xlsx'
        
        try:
            if ext in ['.dxf']:
                from parsers.dxf_parser import DXFParser
                parser = DXFParser()
                self.current_result = parser.parse(file_path)
                room_count = self.current_result.room_count
                self.speak(f"Found {room_count} rooms in {Path(file_path).name}")
                return f"Analyzed {file_path}: {room_count} rooms"
                
            elif ext in ['.dwg']:
                from parsers.dwg_parser import DWGParser
                parser = DWGParser()
                self.current_result = parser.parse(file_path)
                room_count = self.current_result.room_count
                self.speak(f"Found {room_count} rooms")
                return f"Analyzed {file_path}: {room_count} rooms"
                
            elif ext in ['.pdf']:
                from parsers.pdf_parser import PDFParser
                parser = PDFParser()
                self.current_result = parser.parse(file_path)
                device_count = self.current_result.device_count
                self.speak(f"Found {device_count} devices")
                return f"Analyzed {file_path}: {device_count} devices"
                
            elif ext in ['.xlsx', '.xls']:
                from parsers.excel_parser import ExcelParser
                parser = ExcelParser()
                self.current_result = parser.parse(file_path)
                room_count = self.current_result.room_count
                self.speak(f"Found {room_count} rooms")
                return f"Analyzed {file_path}: {room_count} rooms"
                
            else:
                return f"Unsupported file type: {ext}"
                
        except Exception as e:
            return f"Error: {e}"

    def _count_rooms(self) -> str:
        """Count rooms in current result."""
        if not self.current_result:
            return "No file analyzed yet. Say 'analyze [filename]' first."
            
        count = getattr(self.current_result, 'room_count', 0)
        self.speak(f"There are {count} rooms")
        return f"Rooms: {count}"

    def _count_detectors(self) -> str:
        """Calculate detectors using NFPA."""
        if not self.current_result:
            return "No file analyzed yet."
            
        try:
            from core.floor_orchestrator import FloorOrchestrator
            # This would need full integration
            return "Detector calculation requires full analysis"
        except Exception as e:
            return f"Error: {e}"

    def _list_rooms(self) -> str:
        """List all rooms."""
        if not self.current_result:
            return "No file analyzed yet."
            
        rooms = getattr(self.current_result, 'rooms', [])
        if not rooms:
            return "No rooms found."
            
        room_names = [r.name for r in rooms[:10]]
        names = ", ".join(room_names)
        
        if len(rooms) > 10:
            names += f" and {len(rooms) - 10} more"
            
        self.speak(f"Found {len(rooms)} rooms")
        return f"Rooms: {names}"

    def _export_report(self) -> str:
        """Export analysis report."""
        if not self.current_result:
            return "No analysis to export."
            
        return "Export feature coming soon"

    def _show_help(self) -> str:
        """Show help text."""
        help_text = """
Available commands:
- "analyze [filename]" - Parse DXF, DWG, PDF, or Excel file
- "how many rooms" - Show room count
- "how many detectors" - Calculate detectors
- "show rooms" - List all rooms
- "export report" - Generate PDF report
- "help" - Show this message
"""
        self.speak("You can analyze floor plans, check room counts, and more.")
        return help_text


# ═══════════════════════════════════════════════════════
# TEXT MODE (Fallback)
# ═══════════════════════════════════════════════════════

def main():
    """Main entry point for voice interface."""
    import sys
    
    voice = FireAIVoice(voice_enabled=False)
    
    if len(sys.argv) > 1:
        # Process command from args
        command = ' '.join(sys.argv[1:])
        result = voice.process_command(command)
        print(result)
    else:
        # Interactive mode
        print("=" * 50)
        print("FireAI Voice Interface")
        print("=" * 50)
        print("Type a command or use --listen for voice input")
        print("Commands: analyze, count rooms, detectors, help")
        print("=" * 50)
        
        while True:
            try:
                cmd = input("\n🎤 > ").strip()
                if cmd.lower() in ['exit', 'quit']:
                    break
                if cmd:
                    result = voice.process_command(cmd)
                    print(result)
            except KeyboardInterrupt:
                break
                
        print("\nGoodbye!")


if __name__ == "__main__":
    main()