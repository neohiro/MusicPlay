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

        self.theme = {
            "bg": "#1e1e1e",
            "fg": "#ffffff",
            "btn_bg": "#1e1e1e", # Changed to match the main background
            "slider_trough": "#444444",
            "active_bg": "#555555",
            "font_main": ("Helvetica", 12),
            "font_small": ("Helvetica", 10),
            "font_btn": ("Arial", 18),
            # New theme colors for active state
            "active_mode_bg": "#1a5276", # A shade of blue to indicate active mode
        }
        self.root.config(bg=self.theme["bg"])

        self.playlist = []
        self.current_track_index = -1
        self.state = {
            "is_playing": False,
            "is_paused": False,
            "is_dragging_slider": False,
            "last_play_time": 0,
            "paused_time": 0,
            "song_length": 0,
            "is_shuffle_mode": False, # New state variable for shuffle mode
        }
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
        self.progress_slider.bind("<ButtonPress-1>", lambda e: self.state.update({"is_dragging_slider": True}))
        self.progress_slider.bind("<ButtonRelease-1>", self._on_slider_release)
        self.progress_slider.pack(fill=tk.X, expand=True)

        # --- Control Buttons ---
        controls_frame = self._create_widget(tk.Frame)
        controls_frame.pack(pady=20)

        # Updated button list with a command for toggling shuffle mode
        buttons = [
            ("⏮", self.prev_track), ("▶", self.play_music), ("⏸", self.pause_music),
            ("⏹", self.stop_music), ("⏭", self.next_track), ("🎲", self.toggle_shuffle_mode)
        ]
        self.control_buttons = {} # Store button references to update their appearance
        for i, (text, cmd) in enumerate(buttons):
            btn = self._create_widget(tk.Button, controls_frame, text=text, font=self.theme["font_btn"], command=cmd, borderwidth=0, bg=self.theme["btn_bg"], activebackground=self.theme["active_bg"])
            btn.grid(row=0, column=i, padx=10)
            self.control_buttons[text] = btn # Store the button reference

        # --- Volume Slider ---
        self.volume_slider = self._create_widget(
            tk.Scale, from_=1, to=0, orient=tk.VERTICAL, length=50, showvalue=0,
            troughcolor=self.theme["slider_trough"], resolution=0.01, command=self.set_volume
        )
        self.volume_slider.set(0.5)
        self.volume_slider.place(relx=0.98, rely=0.02, anchor='ne')
        self.volume_slider.bind("<MouseWheel>", self._on_mousewheel)
        self.volume_slider.bind("<Button-4>", self._on_mousewheel)
        self.volume_slider.bind("<Button-5>", self._on_mousewheel)

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
        if widget_class in (tk.Label, tk.Button, tk.Scale):
            style["fg"] = self.theme["fg"]
            style["activebackground"] = self.theme["active_bg"]
        return widget_class(master, **{**style, **kwargs})

    # --- Core Logic ---
    def _playback_worker(self):
        """Handles pygame commands in a separate thread."""
        while True:
            command, args = self.command_queue.get()
            try:
                if command == 'load_and_play':
                    pygame.mixer.music.load(args['path'])
                    pygame.mixer.music.play(start=args.get('time', 0))
                elif command == 'play_from_memory':
                    mem_file = io.BytesIO(args['data'])
                    pygame.mixer.music.load(mem_file)
                    pygame.mixer.music.play(start=args.get('time', 0))
                elif command in ['pause', 'unpause', 'stop']:
                    getattr(pygame.mixer.music, command)()
            except Exception as e:
                print(f"Playback Error: {e}")
            finally:
                self.command_queue.task_done()

    def _update_ui_loop(self):
        """Main loop to update time, progress, and check for song end."""
        if self.state["is_playing"] and not self.state["is_paused"]:
            # Check if the song has ended and play the next one
            if not pygame.mixer.music.get_busy() and time.time() - self.state["last_play_time"] > 1.5:
                # The next track logic now depends on the shuffle mode state
                if self.state["is_shuffle_mode"]:
                    self.play_random_track()
                else:
                    self.next_track() # Calls the sequential next track logic
            elif not self.state["is_dragging_slider"]:
                elapsed = time.time() - self.state["last_play_time"]
                if 0 <= elapsed <= self.state["song_length"]:
                    self.time_label.config(text=f"{self._format_time(elapsed)} / {self._format_time(self.state['song_length'])}")
                    self.progress_slider.set(elapsed)
        self.root.after(250, self._update_ui_loop)

    def _update_track_info(self, index):
        """Centralized method to update UI and state for a new track."""
        if not self.playlist or not 0 <= index < len(self.playlist):
            self.track_label.config(text="No track loaded")
            self.state.update({"song_length": 0})
            self.progress_slider.config(to=0)
            self.time_label.config(text="--:-- / --:--")
            return

        self.current_track_index = index
        track_path = self.playlist[self.current_track_index]
        self.state.update({"song_length": self._get_song_length(track_path)})
        self.track_label.config(text=os.path.basename(track_path))
        self.progress_slider.config(to=self.state['song_length'])
        self.time_label.config(text=f"--:-- / {self._format_time(self.state['song_length'])}")

    def _load_and_play_track(self, index, seek_time=0):
        """Loads and plays a specific track by index."""
        if not self.playlist:
            return

        self._update_track_info(index)
        track_path = self.playlist[index]
        self.state.update({
            "is_playing": True,
            "is_paused": False,
            "last_play_time": time.time() - seek_time
        })
        self.command_queue.put(('load_and_play', {'path': track_path, 'time': seek_time}))

    # --- UI Commands ---
    def play_music(self):
        if not self.playlist:
            messagebox.showwarning("No Playlist", "Please load some music files first.")
            return

        if self.state['is_paused']:
            self.state.update({
                "is_paused": False,
                "last_play_time": time.time() - self.state['paused_time']
            })
            self.command_queue.put(('unpause', None))
        elif not self.state['is_playing']:
            self._load_and_play_track(self.current_track_index if self.current_track_index != -1 else 0)

    def pause_music(self):
        if self.state['is_playing'] and not self.state['is_paused']:
            self.state.update({
                "is_paused": True,
                "paused_time": time.time() - self.state['last_play_time']
            })
            self.command_queue.put(('pause', None))

    def stop_music(self):
        if self.state['is_playing']:
            self.command_queue.put(('stop', None))
            self.state.update({"is_playing": False, "is_paused": False})
            self.progress_slider.set(0)
            if self.playlist:
                self.time_label.config(text=f"--:-- / {self._format_time(self.state['song_length'])}")

    def next_track(self):
        """Plays the next track in the sequence."""
        if not self.playlist: return
        self.stop_music()
        
        # New logic: Check if shuffle mode is on
        if self.state["is_shuffle_mode"]:
            self.play_random_track() # Call the new random method
        else:
            next_index = (self.current_track_index + 1) % len(self.playlist)
            self._load_and_play_track(next_index)

    def prev_track(self):
        if not self.playlist: return
        self.stop_music()
        prev_index = (self.current_track_index - 1 + len(self.playlist)) % len(self.playlist)
        self._load_and_play_track(prev_index)

    def toggle_shuffle_mode(self):
        """Toggles the shuffle mode and updates the button color."""
        self.state["is_shuffle_mode"] = not self.state["is_shuffle_mode"]
        btn = self.control_buttons.get("🎲")
        if btn:
            if self.state["is_shuffle_mode"]:
                btn.config(bg=self.theme["active_mode_bg"])
            else:
                btn.config(bg=self.theme["btn_bg"])

    def play_random_track(self):
        """Selects and plays a random track, used by both the button and the main loop."""
        if len(self.playlist) < 2: return
        self.stop_music()
        random_index = random.randint(0, len(self.playlist) - 1)
        self._load_and_play_track(random_index)

    def load_files(self):
        supported_formats = ["mp3", "ogg", "flac", "m4a", "aac", "opus", "wav", "wma"]
        file_types = [("Audio Files", " ".join(f"*.{ext}" for ext in supported_formats))]
        files = filedialog.askopenfilenames(filetypes=file_types)
        self._handle_loaded_files(files)

    def load_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            supported_formats = (".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wav", ".wma")
            files = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs if f.lower().endswith(supported_formats)]
            self._handle_loaded_files(files, show_warning=True)

    def _handle_loaded_files(self, files, show_warning=False):
        """Handles loading logic for both single files and folders."""
        if files:
            self.stop_music()
            self.playlist = sorted(list(files))
            self._load_and_play_track(0)
        elif show_warning:
            messagebox.showwarning("No Music", "No audio files found.")

    def set_volume(self, val):
        pygame.mixer.music.set_volume(float(val))

    # --- Event Handlers ---
    def _on_mousewheel(self, event):
        """Changes the volume with the mouse scroll wheel, cross-platform."""
        current_volume = self.volume_slider.get()
        delta = 0.05 if event.num == 4 or event.delta > 0 else -0.05
        new_volume = max(0.0, min(1.0, current_volume + delta))
        self.volume_slider.set(new_volume)

    def _on_slider_move(self, value_str):
        """Updates time label as user drags the slider."""
        if self.state['is_dragging_slider']:
            elapsed = float(value_str)
            self.time_label.config(text=f"{self._format_time(elapsed)} / {self._format_time(self.state['song_length'])}")

    def _on_slider_release(self, event):
        """Seeks to the new position when the slider is released."""
        if self.state['is_dragging_slider']:
            self.state.update({"is_dragging_slider": False})
            if self.state['is_playing']:
                self._load_and_play_track(self.current_track_index, seek_time=self.progress_slider.get())

    # --- Utility Methods ---
    @staticmethod
    def _format_time(seconds):
        """Formats seconds into HH:MM:SS or MM:SS format."""
        if seconds is None:
            return "--:--"
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
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
    app = MusicPlayer(root)
    try:
        root.iconbitmap('icon.ico')
    except tk.TclError:
        pass
    root.mainloop()
