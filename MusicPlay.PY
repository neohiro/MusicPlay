import tkinter as tk
from tkinter import filedialog, messagebox
import pygame
import os
import random
import time
import threading
import queue
from mutagen import File
import io

# Initialize pygame mixer with a larger buffer for smoother playback
pygame.mixer.pre_init(44100, -16, 2, 2048)
pygame.mixer.init()

class MusicPlayer:
    """A threaded music player application using Tkinter and Pygame."""
    def __init__(self, root):
        self.root = root
        self.root.title("Python Music Player")
        self.root.resizable(False, False)

        # --- Theme and Styling ---
        self.theme = {
            "bg": "#1e1e1e",
            "fg": "#ffffff",
            "btn_bg": "#333333",
            "slider_trough": "#444444",
            "active_bg": "#555555",
            "font_main": ("Helvetica", 12),
            "font_small": ("Helvetica", 10),
            "font_btn": ("Arial", 18),
        }
        self.root.config(bg=self.theme["bg"])

        # --- State Management ---
        self.playlist = []
        self.current_track_index = 0
        self.playback_state = {
            "playing": False,
            "paused": False,
            "dragging_slider": False,
            "start_time": 0,
            "paused_time": 0,
            "song_length": 0,
            "in_memory_data": None, # Store file data in memory
        }

        # --- Threading ---
        self.command_queue = queue.Queue()
        threading.Thread(target=self._playback_worker, daemon=True).start()

        self._setup_ui()
        self.root.after(250, self._update_ui_loop)

    def _setup_ui(self):
        """Creates and packs all UI widgets."""
        # --- Track Info ---
        self.track_label = self._create_widget(tk.Label, text="No track loaded", wraplength=380, font=self.theme["font_main"])
        self.track_label.pack(pady=15)

        # --- Progress Bar and Time ---
        progress_frame = self._create_widget(tk.Frame)
        progress_frame.pack(pady=5, fill=tk.X, padx=25)

        self.time_label = self._create_widget(tk.Label, progress_frame, text="--:-- / --:--", font=self.theme["font_small"])
        self.time_label.pack()

        self.progress_slider = self._create_widget(
            tk.Scale, progress_frame, from_=0, to=100, orient=tk.HORIZONTAL, showvalue=0,
            troughcolor=self.theme["slider_trough"], resolution=0.1, command=self._on_slider_move
        )
        self.progress_slider.bind("<ButtonPress-1>", lambda e: self._set_state(dragging_slider=True))
        self.progress_slider.bind("<ButtonRelease-1>", self._on_slider_release)
        self.progress_slider.pack(fill=tk.X, expand=True)

        # --- Control Buttons ---
        controls_frame = self._create_widget(tk.Frame)
        controls_frame.pack(pady=20)
        buttons = {
            "⏮": self.prev_track, "▶": self.play_music, "⏸": self.pause_music,
            "⏹": self.stop_music, "⏭": self.next_track, "🎲": self.random_track
        }
        for i, (text, cmd) in enumerate(buttons.items()):
            btn = self._create_widget(tk.Button, controls_frame, text=text, font=self.theme["font_btn"], command=cmd, borderwidth=0, activebackground=self.theme["active_bg"])
            btn.grid(row=0, column=i, padx=10)

        # --- Volume Slider ---
        self.volume_slider = self._create_widget(
            tk.Scale, from_=1, to=0, orient=tk.VERTICAL, length=50, showvalue=0,
            troughcolor=self.theme["slider_trough"], resolution=0.01, command=self.set_volume
        )
        self.volume_slider.set(0.5)
        self.volume_slider.place(relx=0.98, rely=0.02, anchor='ne')
        self.volume_slider.bind("<MouseWheel>", self._on_mousewheel) # Windows & macOS
        self.volume_slider.bind("<Button-4>", self._on_mousewheel)    # Linux scroll up
        self.volume_slider.bind("<Button-5>", self._on_mousewheel)    # Linux scroll down

        # --- File Loading Buttons ---
        load_frame = self._create_widget(tk.Frame)
        load_frame.pack(pady=20, fill=tk.X, padx=20)
        self.load_button = self._create_widget(tk.Button, load_frame, text="📂 Load Files", command=self.load_files, activebackground=self.theme["active_bg"])
        self.load_folder_button = self._create_widget(tk.Button, load_frame, text="📁 Load Folder", command=self.load_folder, activebackground=self.theme["active_bg"])
        self.load_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.load_folder_button.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

    def _create_widget(self, widget_class, master=None, **kwargs):
        """Helper to create themed widgets."""
        if master is None: master = self.root
        style = {"bg": self.theme["bg"], "highlightbackground": self.theme["bg"]}
        if widget_class in (tk.Label, tk.Button, tk.Scale): style["fg"] = self.theme["fg"]
        if widget_class is tk.Button: style["activebackground"] = self.theme["active_bg"]
        return widget_class(master, **{**style, **kwargs})

    # --- Core Logic ---
    def _playback_worker(self):
        """Handles pygame commands in a separate thread."""
        while True:
            command, args = self.command_queue.get()
            try:
                if command == 'play':
                    pygame.mixer.music.load(args['path'])
                    pygame.mixer.music.play(start=args.get('time', 0))
                elif command == 'play_from_memory':
                    mem_file = io.BytesIO(args['data'])
                    pygame.mixer.music.load(mem_file)
                    pygame.mixer.music.play(start=args.get('time', 0))
                else:
                    getattr(pygame.mixer.music, command)()
            except Exception as e:
                print(f"Playback Error: {e}")
            finally:
                self.command_queue.task_done()

    def _update_ui_loop(self):
        """Main loop to update time, progress, and check for song end."""
        state = self.playback_state
        if state['playing'] and not pygame.mixer.music.get_busy() and not state['paused']:
            if time.time() - state['start_time'] > 1.5:
                self.next_track()
        elif state['playing'] and not state['paused'] and not state['dragging_slider']:
            elapsed = time.time() - state['start_time']
            if 0 <= elapsed <= state['song_length']:
                self.time_label.config(text=f"{self._format_time(elapsed)} / {self._format_time(state['song_length'])}")
                self.progress_slider.set(elapsed)
        self.root.after(250, self._update_ui_loop)

    def _set_state(self, **kwargs):
        """Safely updates the playback state."""
        self.playback_state.update(kwargs)

    def _load_playlist(self, files):
        """Handles loading and resetting the playlist."""
        if files:
            self.playlist = sorted(list(files))
            self.current_track_index = 0
            self.stop_music()
            self._update_track_display()
            with open(self.playlist[self.current_track_index], 'rb') as f:
                self.playback_state['in_memory_data'] = f.read()

    def _update_track_display(self):
        """Updates UI elements for the current track."""
        if not self.playlist: return
        track_path = self.playlist[self.current_track_index]
        self._set_state(song_length=self._get_song_length(track_path))
        self.track_label.config(text=os.path.basename(track_path))
        self.progress_slider.config(to=self.playback_state['song_length'])
        self.time_label.config(text=f"--:-- / {self._format_time(self.playback_state['song_length'])}")

    # --- UI Commands ---
    def play_music(self):
        if not self.playlist: return
        if self.playback_state['paused']:
            self._set_state(paused=False, start_time=time.time() - self.playback_state['paused_time'])
            self.command_queue.put(('unpause', None))
        else:
            self._start_playback()

    def pause_music(self):
        if self.playback_state['playing'] and not self.playback_state['paused']:
            self._set_state(paused=True, paused_time=time.time() - self.playback_state['start_time'])
            self.command_queue.put(('pause', None))

    def stop_music(self):
        if self.playback_state['playing']:
            self.command_queue.put(('stop', None))
            self._set_state(playing=False, paused=False, start_time=0)
            self.progress_slider.set(0)
            if self.playlist:
                self.time_label.config(text=f"--:-- / {self._format_time(self.playback_state['song_length'])}")

    def _start_playback(self, seek_time=None):
        """Central method to start or seek a track, using in-memory data."""
        self._update_track_display()
        start = time.time() - (seek_time or 0)
        self._set_state(playing=True, paused=False, start_time=start)

        if self.playback_state['in_memory_data']:
            self.command_queue.put(('play_from_memory', {'data': self.playback_state['in_memory_data'], 'time': seek_time or 0}))
        else:
            path = self.playlist[self.current_track_index]
            self.command_queue.put(('play', {'path': path, 'time': seek_time or 0}))

    def _change_track(self, delta):
        if not self.playlist: return
        self.stop_music()
        self.current_track_index = (self.current_track_index + delta) % len(self.playlist)
        with open(self.playlist[self.current_track_index], 'rb') as f:
            self.playback_state['in_memory_data'] = f.read()
        self._start_playback()

    def next_track(self): self._change_track(1)
    def prev_track(self): self._change_track(-1)

    def random_track(self):
        if len(self.playlist) < 2: return
        self.stop_music()
        self.current_track_index = random.randint(0, len(self.playlist) - 1)
        with open(self.playlist[self.current_track_index], 'rb') as f:
            self.playback_state['in_memory_data'] = f.read()
        self._start_playback()

    def load_files(self):
        supported_formats = ["mp3", "ogg", "flac", "m4a", "aac", "opus", "wav", "wma"]
        file_types = [("Audio Files", " ".join(f"*.{ext}" for ext in supported_formats))]
        files = filedialog.askopenfilenames(filetypes=file_types)
        if files:
            self.playlist = sorted(list(files))
            self.current_track_index = 0
            self.stop_music()
            with open(self.playlist[0], 'rb') as f:
                self.playback_state['in_memory_data'] = f.read()
            self._update_track_display()

    def load_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            supported_formats = (".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wav", ".wma")
            files = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs if f.lower().endswith(supported_formats)]
            if files:
                self.playlist = sorted(files)
                self.current_track_index = 0
                self.stop_music()
                with open(self.playlist[0], 'rb') as f:
                    self.playback_state['in_memory_data'] = f.read()
                self._update_track_display()
            else: messagebox.showwarning("No Music", "No audio files found.")

    def set_volume(self, val):
        pygame.mixer.music.set_volume(float(val))

    # --- Event Handlers ---
    def _on_mousewheel(self, event):
        """Changes the volume with the mouse scroll wheel, cross-platform."""
        current_volume = self.volume_slider.get()
        delta = 0
        if event.num == 4 or event.delta > 0:
            delta = 0.05
        elif event.num == 5 or event.delta < 0:
            delta = -0.05
        
        new_volume = max(0.0, min(1.0, current_volume + delta))
        self.volume_slider.set(new_volume)

    def _on_slider_move(self, value_str):
        """Updates time label as user drags the slider."""
        if self.playback_state['dragging_slider']:
            elapsed = float(value_str)
            self.time_label.config(text=f"{self._format_time(elapsed)} / {self._format_time(self.playback_state['song_length'])}")

    def _on_slider_release(self, event):
        """Seeks to the new position when the slider is released."""
        if self.playback_state['dragging_slider']:
            self._set_state(dragging_slider=False)
            if self.playback_state['playing']:
                self._start_playback(seek_time=self.progress_slider.get())

    # --- Utility Methods ---
    @staticmethod
    def _format_time(seconds):
        """Formats seconds into HH:MM:SS or MM:SS format, correctly handling hours."""
        if seconds is None:
            return "--:--"
        
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _get_song_length(file_path):
        try:
            audio = File(file_path)
            return audio.info.length
        except Exception as e:
            print(f"Error getting length for {file_path}: {e}")
            return 0

if __name__ == "__main__":
    root = tk.Tk()
    root.iconbitmap('icon.ico')  # Added this line to set the icons
    app = MusicPlayer(root)
    root.mainloop()