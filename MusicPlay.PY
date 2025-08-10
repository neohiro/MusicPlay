import tkinter as tk
from tkinter import filedialog, messagebox
import pygame
import os
import random
import time
import threading
import queue
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

# You need to install mutagen: pip install mutagen
# Initialize pygame mixer with a larger buffer before pygame.init() is called
# This should be done before any other pygame module is initialized.
pygame.mixer.pre_init(44100, -16, 2, 8192) # frequency, size, channels, buffer
pygame.mixer.init()

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Music Player")
        
        # Make the window size fit the content and prevent resizing
        self.root.resizable(False, False)
        
        # Dark Theme Colors
        bg_color = "#1e1e1e"
        fg_color = "#ffffff"
        button_bg = "#333333"
        slider_trough = "#444444"

        self.root.config(bg=bg_color)
        
        # State variables
        self.playlist = []
        self.current_track_index = 0
        self.paused = False
        self.song_length = 0
        self.song_start_time = 0
        self.paused_time = 0
        self.is_seeking = False
        
        # New variable to prevent the progress bar from updating while the user is dragging it
        self.is_dragging_slider = False

        # Threading Setup
        self.playback_command_queue = queue.Queue()
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()

        # UI Elements
        
        # Track Info Label
        self.track_label = tk.Label(root, text="No track loaded", wraplength=380, font=("Helvetica", 12),
                                     bg=bg_color, fg=fg_color)
        self.track_label.pack(pady=15)
        
        # Progress Frame (for alignment)
        progress_frame = tk.Frame(root, bg=bg_color)
        progress_frame.pack(pady=5, fill=tk.X, padx=25)

        self.time_label = tk.Label(progress_frame, text="--:-- / --:--", font=("Helvetica", 10),
                                   bg=bg_color, fg=fg_color)
        self.time_label.pack()
        
        self.progress_slider = tk.Scale(progress_frame, from_=0, to=100, resolution=1,
                                         orient=tk.HORIZONTAL,
                                         showvalue=0, relief=tk.GROOVE,
                                         bg=bg_color, fg=fg_color,
                                         troughcolor=slider_trough,
                                         highlightbackground=bg_color,
                                         activebackground=button_bg)
        # Bind mouse events to the slider
        self.progress_slider.bind("<Button-1>", self.start_slider_drag)
        # Bind the mouse release to the root window so the user can release anywhere
        self.root.bind("<ButtonRelease-1>", self.handle_slider_release)
        self.progress_slider.pack(fill=tk.X, expand=True)

        # Main Controls Frame
        controls_frame = tk.Frame(root, bg=bg_color)
        controls_frame.pack(pady=20)
        
        btn_font = ("Arial", 18)
        self.prev_button = tk.Button(controls_frame, text="⏮", font=btn_font, command=self.prev_track,
                                     borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.play_button = tk.Button(controls_frame, text="▶", font=btn_font, command=self.play_music,
                                     borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.pause_button = tk.Button(controls_frame, text="⏸", font=btn_font, command=self.pause_music,
                                      borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.stop_button = tk.Button(controls_frame, text="⏹", font=btn_font, command=self.stop_music,
                                     borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.next_button = tk.Button(controls_frame, text="⏭", font=btn_font, command=self.next_track,
                                     borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.random_button = tk.Button(controls_frame, text="🎲", font=btn_font, command=self.random_track,
                                      borderwidth=0, bg=button_bg, fg=fg_color, activebackground=bg_color)

        self.prev_button.grid(row=0, column=0, padx=10)
        self.play_button.grid(row=0, column=1, padx=10)
        self.pause_button.grid(row=0, column=2, padx=10)
        self.stop_button.grid(row=0, column=3, padx=10)
        self.next_button.grid(row=0, column=4, padx=10)
        self.random_button.grid(row=0, column=5, padx=10)

        # Volume Slider: Removed label and shifted to the right
        self.volume_slider = tk.Scale(root, from_=1, to=0, resolution=0.001,
                                         orient=tk.VERTICAL, command=self.set_volume, length=50, showvalue=0,
                                         bg=bg_color, fg=fg_color,
                                         troughcolor=slider_trough,
                                         highlightbackground=bg_color,
                                         activebackground=button_bg)
        self.volume_slider.set(0.5)
        pygame.mixer.music.set_volume(0.5)
        self.volume_slider.place(relx=0.98, rely=0.02, anchor='ne')
        self.volume_slider.bind("<MouseWheel>", self.on_mousewheel)

        # File Loading Frame
        load_frame = tk.Frame(root, bg=bg_color)
        load_frame.pack(pady=20, fill=tk.X, padx=20)
        
        self.load_button = tk.Button(load_frame, text="📂 Load Files", command=self.load_music,
                                     bg=button_bg, fg=fg_color, activebackground=bg_color)
        self.load_folder_button = tk.Button(load_frame, text="📁 Load Folder", command=self.load_music_folder,
                                           bg=button_bg, fg=fg_color, activebackground=bg_color)
        
        self.load_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.load_folder_button.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

        self.root.after(1000, self.check_song_end)

    def _playback_worker(self):
        """Worker thread to handle all pygame playback to avoid UI freezing."""
        while True:
            command, *args = self.playback_command_queue.get()
            try:
                if command == 'play':
                    pygame.mixer.music.load(args[0])
                    pygame.mixer.music.play()
                    self.is_seeking = False
                elif command == 'pause':
                    pygame.mixer.music.pause()
                elif command == 'unpause':
                    pygame.mixer.music.unpause()
                elif command == 'stop':
                    pygame.mixer.music.stop()
                elif command == 'seek':
                    file_path, seek_time = args[0]
                    pygame.mixer.music.stop()
                    pygame.mixer.music.load(file_path)
                    pygame.mixer.music.play(start=seek_time)
                    self.is_seeking = False
            except Exception as e:
                print(f"Error in playback thread: {e}")
            finally:
                self.playback_command_queue.task_done()

    def format_time(self, seconds):
        if seconds is None or seconds < 0: return "--:--"
        return time.strftime('%M:%S', time.gmtime(seconds))

    def get_song_length(self, file_path):
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mp3': audio = MP3(file_path)
            elif ext == '.wav': audio = WAVE(file_path)
            else: return 0
            return audio.info.length
        except Exception:
            return 0

    def update_track_info(self):
        track_path = self.playlist[self.current_track_index]
        self.track_label.config(text=os.path.basename(track_path))
        self.song_length = self.get_song_length(track_path)
        self.progress_slider.config(to=self.song_length)
        self.time_label.config(text=f"--:-- / {self.format_time(self.song_length)}")

    def load_music_common(self):
        if self.playlist:
            self.stop_music()
            self.current_track_index = 0
            self.update_track_info()

    def load_music(self):
        files = filedialog.askopenfilenames(filetypes=[("Audio Files", "*.mp3 *.wav")])
        if files:
            self.playlist = list(files)
            self.load_music_common()

    def load_music_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            files = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs if f.lower().endswith((".mp3", ".wav"))]
            if files:
                self.playlist = sorted(files)
                self.load_music_common()
            else:
                messagebox.showwarning("No Music Found", "No audio files in this folder.")
    
    def play_music(self):
        """Handles the play button, either starting a new track or unpausing."""
        if not self.playlist: return
        
        if self.paused:
            self.paused = False
            self.song_start_time = time.time() - self.paused_time
            self.playback_command_queue.put(('unpause',))
        else:
            # This is for playing a song from the start
            self.update_track_info()
            self.song_start_time = time.time()
            track_path = self.playlist[self.current_track_index]
            self.playback_command_queue.put(('play', track_path))
        
        # Always start the update loop when play is initiated
        self.update_progress()
        
    def pause_music(self):
        """Pauses the currently playing music."""
        if pygame.mixer.music.get_busy() and not self.paused:
            self.paused = True
            self.paused_time = time.time() - self.song_start_time
            self.playback_command_queue.put(('pause',))
    
    def stop_music(self):
        self.playback_command_queue.put(('stop',))
        self.paused = False
        self.song_start_time = 0
        self.progress_slider.set(0)
        total_duration = self.format_time(self.song_length)
        self.time_label.config(text=f"--:-- / {total_duration}" if self.playlist else "--:-- / --:--")

    def change_track(self, index_change):
        """Changes to the next or previous track and plays it."""
        if not self.playlist: return
        self.current_track_index = (self.current_track_index + index_change) % len(self.playlist)
        self.paused = False  # Ensure the new track is not paused
        self.play_music()

    def next_track(self): self.change_track(1)
    def prev_track(self): self.change_track(-1)

    def random_track(self):
        if not self.playlist or len(self.playlist) < 2: return
        self.current_track_index = random.randint(0, len(self.playlist) - 1)
        self.paused = False
        self.play_music()
        
    def set_volume(self, val):
        pygame.mixer.music.set_volume(float(val))

    def on_mousewheel(self, event):
        """Changes the volume with the mouse scroll wheel."""
        current_volume = self.volume_slider.get()
        if event.delta > 0: # Scroll up
            new_volume = current_volume + 0.01 
        else: # Scroll down
            new_volume = current_volume - 0.01 
        
        # Clamp the volume between 0 and 1
        new_volume = max(0, min(1, new_volume))
        
        self.volume_slider.set(new_volume)

    def start_slider_drag(self, event):
        """Set a flag when the user starts dragging the slider."""
        self.is_dragging_slider = True

    def handle_slider_release(self, event):
        """Handles the mouse release event anywhere on the root window."""
        if self.is_dragging_slider and self.playlist:
            # We must be dragging the slider to perform a seek
            seek_time = self.progress_slider.get()
            self.song_start_time = time.time() - seek_time
            track_path = self.playlist[self.current_track_index]
            self.is_seeking = True
            self.playback_command_queue.put(('seek', (track_path, seek_time)))

        # Reset the drag flag regardless of where the release happened
        self.is_dragging_slider = False

    def update_progress(self):
        """Robustly updates the UI and reschedules itself."""
        # A song is intended to be playing if it's not paused and not stopped.
        playback_intended = not self.paused and self.song_start_time != 0

        # Don't update the slider if the user is dragging it or if a seek is in progress
        if playback_intended and not self.is_dragging_slider and not self.is_seeking:
            # Only update the text if pygame is actually busy
            if pygame.mixer.music.get_busy():
                elapsed_time = time.time() - self.song_start_time
                if 0 <= elapsed_time <= self.song_length:
                    self.time_label.config(text=f"{self.format_time(elapsed_time)} / {self.format_time(self.song_length)}")
                    self.progress_slider.set(elapsed_time)
            
            # ALWAYS reschedule if playback is intended. This prevents the loop
            # from dying if it runs before the song has started in the thread.
            self.root.after(1000, self.update_progress)
        elif self.is_seeking:
            # Continue to check for completion of seeking operation
            self.root.after(100, self.update_progress)
        else:
            # If nothing is playing, the loop stops here until a song starts again
            pass


    def check_song_end(self):
        """Checks if the current song has finished and moves to the next."""
        if not self.paused and self.song_start_time != 0 and not pygame.mixer.music.get_busy():
            # If the song is no longer busy and it was playing, it must have ended.
            # A small time check avoids false positives at the very start of a track.
            if time.time() - self.song_start_time > 1.5: # 1.5s buffer
                self.next_track()
        
        # Keep this check running continuously
        self.root.after(1000, self.check_song_end)

if __name__ == "__main__":
    root = tk.Tk()
    app = MusicPlayer(root)
    root.mainloop()
