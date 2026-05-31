"""Read the clipboard aloud — fully offline via AVSpeechSynthesizer.

Detects the text's language (NaturalLanguage), picks a matching system voice, and
speaks. Press the trigger again while speaking to stop (toggle). No internet,
no key — uses the macOS built-in voices.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_AV_BOUNDARY_IMMEDIATE = 0


class Speaker:
    def __init__(self, voice_name: str = "") -> None:
        from AVFoundation import AVSpeechSynthesizer

        self._synth = AVSpeechSynthesizer.alloc().init()
        self._voice_name = (voice_name or "").strip()

    def toggle(self, text: str | None) -> str:
        """Main-thread only. Returns 'speaking' | 'stopped' | 'empty'."""
        from AVFoundation import AVSpeechUtterance

        if self._synth.isSpeaking():
            self._synth.stopSpeakingAtBoundary_(_AV_BOUNDARY_IMMEDIATE)
            return "stopped"

        text = (text or "").strip()
        if not text:
            return "empty"

        utt = AVSpeechUtterance.speechUtteranceWithString_(text)
        voice = self._voice_for(self._detect(text))
        if voice is not None:
            utt.setVoice_(voice)
        self._synth.speakUtterance_(utt)
        return "speaking"

    def stop(self) -> None:
        """Main-thread only. Stop any ongoing speech and free the audio device."""
        if self._synth.isSpeaking():
            self._synth.stopSpeakingAtBoundary_(_AV_BOUNDARY_IMMEDIATE)

    def is_speaking(self) -> bool:
        return bool(self._synth.isSpeaking())

    @staticmethod
    def _detect(text: str):
        try:
            from NaturalLanguage import NLLanguageRecognizer

            rec = NLLanguageRecognizer.alloc().init()
            rec.processString_(text[:400])
            lang = rec.dominantLanguage()
            return str(lang) if lang else None
        except Exception as exc:  # noqa: BLE001
            log.warning("language detect failed: %s", exc)
            return None

    def _voice_for(self, lang: str | None):
        from AVFoundation import AVSpeechSynthesisVoice

        voices = AVSpeechSynthesisVoice.speechVoices()

        # 1) explicit override by exact voice name.
        if self._voice_name:
            for v in voices:
                if str(v.name()).lower() == self._voice_name.lower():
                    return v

        if not lang:
            return None
        matching = [v for v in voices if str(v.language()).lower().startswith(lang.lower())]
        if not matching:
            return None

        # 2) the system's standard voice for the language (not a novelty voice).
        default = AVSpeechSynthesisVoice.voiceWithLanguage_(lang) or matching[0]
        # 3) prefer a higher-quality version of that same voice (Enhanced/Premium).
        best = default
        for v in matching:
            if str(v.name()) == str(default.name()) and v.quality() > best.quality():
                best = v
        # 4) otherwise, any higher-quality matching voice beats the compact default.
        if best is default:
            higher = [v for v in matching if v.quality() > default.quality()]
            if higher:
                best = max(higher, key=lambda v: v.quality())
        return best
