import json
import os
import numpy as np
import pyaudiowpatch as pyaudio
from vosk import Model, KaldiRecognizer
from datetime import datetime

# Initialize Model
model = Model(lang="en-us")

def transcribe_to_file():

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"Meeting_Notes_{timestamp_str}.txt"

    print(f"Saving transcription to: {log_filename}")
    print("Recording... Press Ctrl+C to stop.\n")

    with pyaudio.PyAudio() as p:
        try:
            # Setup loopback device (speaker capture)
            default_speakers = p.get_default_output_device_info()
            loopback_devices = p.get_loopback_device_info_generator()

            target_device = next(
                (d for d in loopback_devices if default_speakers["name"] in d["name"]),
                None
            )

            if not target_device:
                print("Error: Could not find loopback device.")
                return

            actual_rate = int(target_device["defaultSampleRate"])

            rec = KaldiRecognizer(model, actual_rate)

            stream = p.open(
                format=pyaudio.paInt16,
                channels=2,
                rate=actual_rate,
                input=True,
                input_device_index=target_device["index"],
                frames_per_buffer=4000
            )

            with open(log_filename, "a", encoding="utf-8") as f:

                f.write(
                    f"MEETING TRANSCRIPT\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    + "="*40 + "\n\n"
                )

                while True:

                    data = stream.read(2000, exception_on_overflow=False)

                    audio_data = np.frombuffer(data, dtype=np.int16)

                    mono_data = audio_data[::2].tobytes()

                    if rec.AcceptWaveform(mono_data):

                        res = json.loads(rec.Result())

                        text = res.get("text", "").strip()

                        if text:

                            current_time = datetime.now().strftime("%H:%M:%S")

                            entry = f"[{current_time}] {text}"

                            f.write(entry + "\n\n")
                            f.flush()

        except KeyboardInterrupt:

            print("\nStopping transcription...")
            os.startfile(log_filename)

        except Exception as e:

            print(f"Error: {e}")

        finally:

            if 'stream' in locals():
                stream.close()


if __name__ == "__main__":
    transcribe_to_file()