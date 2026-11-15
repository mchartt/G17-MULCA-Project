"""
MULCA in a Discord voice channel: per-user capture, one speaker at a time
up to MUCA-Server, and spoken replies played back -- the Discord equivalent
of the Unity client's Remote orchestration.
"""

from .bridge import VoiceBridge
from .player import AssistantPlayer
from .synchronizer import SpeakerSynchronizer

__all__ = [
    "AssistantPlayer",
    "SpeakerSynchronizer",
    "VoiceBridge",
]
