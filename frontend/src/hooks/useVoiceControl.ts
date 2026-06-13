import { useState, useEffect, useCallback } from 'react';
import { actions } from '@/store/simpleStore';

export function useVoiceControl() {
  const [isListening, setIsListening] = useState(false);
  const [recognition, setRecognition] = useState<any>(null);

  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = 'en-US'; // English supported mostly

      rec.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript.toLowerCase();
        if (import.meta.env.DEV) console.log('Voice Command Received:', transcript);
        
        // Handle commands
        if (transcript.includes('add generator')) {
          actions.addElement({
            id: `gen-${Date.now()}`,
            type: 'generator',
            x: 100, y: 100,
            voltage: 11000
          });
        } else if (transcript.includes('add battery')) {
          actions.addElement({
            id: `bat-${Date.now()}`,
            type: 'battery',
            x: 200, y: 200,
            voltage: 220
          });
        } else if (transcript.includes('add panel')) {
          actions.addElement({
            id: `pan-${Date.now()}`,
            type: 'panel',
            x: 300, y: 300,
            voltage: 220
          });
        } else if (transcript.includes('clear errors')) {
          actions.clearErrors();
        } else {
          actions.pushError({
            message: `Unknown voice command: "${transcript}"`,
          });
        }
        
        setIsListening(false);
        actions.setVoiceActive(false);
      };

      rec.onerror = (event: any) => {
        if (import.meta.env.DEV) console.error('Speech recognition error', event.error);
        setIsListening(false);
        actions.setVoiceActive(false);
        actions.pushError({
          message: `Speech recognition error: ${event.error}`,
        });
      };

      rec.onend = () => {
        setIsListening(false);
        actions.setVoiceActive(false);
      };

      setRecognition(rec);
    }
  }, []);

  const startListening = useCallback(() => {
    if (recognition) {
      try {
        recognition.start();
        setIsListening(true);
        actions.setVoiceActive(true);
      } catch (e) {
        if (import.meta.env.DEV) console.error("Failed to start recognition", e);
      }
    } else {
      actions.pushError({
        message: 'Speech Recognition not supported in this browser.',
      });
    }
  }, [recognition]);

  const stopListening = useCallback(() => {
    if (recognition) {
      recognition.stop();
      setIsListening(false);
      actions.setVoiceActive(false);
    }
  }, [recognition]);

  return { isListening, startListening, stopListening };
}
