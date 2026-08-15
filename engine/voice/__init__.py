"""
AirOS — Voice subsystem.
Local wake word ("jarvis"), command STT, intent parsing, and TTS output.
"""

from engine.voice.audio import MicrophoneStream, rms_level
from engine.voice.recognizer import VoskRecognizer
from engine.voice.speech_output import SpeechOutput
from engine.voice.intent import parse_intent, ParsedIntent
from engine.voice.assistant import VoiceAssistant

__all__ = [
    "MicrophoneStream",
    "rms_level",
    "VoskRecognizer",
    "SpeechOutput",
    "parse_intent",
    "ParsedIntent",
    "VoiceAssistant",
]
