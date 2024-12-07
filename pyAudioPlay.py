import os
import pygame
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinterdnd2 import DND_FILES, TkinterDnD
from mutagen import File
import sqlite3
import traceback
import logging
import time
import threading

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)

class CircularQueue:
    def __init__(self):
        self.queue = []
        self.current_index = -1

    def add(self, item):
        self.queue.append(item)
        if self.current_index == -1:
            self.current_index = 0

    def next(self):
        if not self.queue:
            logging.warning("Queue is empty")
            return None
        self.current_index = (self.current_index + 1) % len(self.queue)
        return self.queue[self.current_index]

    def previous(self):
        if not self.queue:
            logging.warning("Queue is empty")
            return None
        self.current_index = (self.current_index - 1) % len(self.queue)
        return self.queue[self.current_index]

    def current(self):
        if not self.queue or self.current_index == -1:
            logging.warning("No current item in queue")
            return None
        return self.queue[self.current_index]

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Player")
        self.root.geometry("500x500")
        self.root.resizable(True, True)
        
        self.directory = ""
        self.song_queue = CircularQueue()
        self.paused = False
        self.volume = 1.0
        self.current_time = 0
        self.total_duration = 0
        self.is_seeking = False
        self.current_song_path = None

        self.create_database()

        self.create_widgets()

        self.load_stored_directories()
        
        self.progress_thread = threading.Thread(target=self.track_progress, daemon=True)
        self.progress_thread.start()

    def create_database(self):
        try:
            conn = sqlite3.connect('music_player.db')
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS directories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE
                )
            ''')
            conn.commit()
            conn.close()
            logging.info("Database created successfully")
        except Exception as e:
            logging.error(f"Error creating database: {e}")

    def create_widgets(self):
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.drop_files)

            self.song_info_frame = tk.Frame(self.root)
            self.song_info_frame.pack(pady=10)

            self.song_name_label = tk.Label(self.song_info_frame, text="Song: ", font=("Helvetica", 12), wraplength=350)
            self.song_name_label.pack(side=tk.TOP, padx=10, pady=5)

            self.artist_label = tk.Label(self.song_info_frame, text="Artist: ", font=("Helvetica", 12))
            self.artist_label.pack(side=tk.TOP, padx=10, pady=5)

            self.progress_frame = tk.Frame(self.root)
            self.progress_frame.pack(pady=10, padx=20, fill=tk.X)

            self.time_label = tk.Label(self.progress_frame, text="0:00 / 0:00")
            self.time_label.pack(side=tk.TOP, fill=tk.X)

            self.progress_bar = ttk.Scale(
                self.progress_frame, 
                from_=0, 
                to=100, 
                orient=tk.HORIZONTAL, 
                command=self.on_progress_change
            )
            self.progress_bar.pack(side=tk.TOP, fill=tk.X)

            self.volume_frame = tk.Frame(self.root)
            self.volume_frame.pack(pady=10, padx=20, fill=tk.X)

            self.volume_label = tk.Label(self.volume_frame, text="Volume:")
            self.volume_label.pack(side=tk.LEFT, padx=5)

            self.volume_slider = ttk.Scale(
                self.volume_frame, 
                from_=0, 
                to=100, 
                orient=tk.HORIZONTAL, 
                command=self.on_volume_change
            )
            self.volume_slider.set(100)  
            self.volume_slider.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

            self.control_frame = tk.Frame(self.root)
            self.control_frame.pack(pady=20)

            self.load_directory_button = tk.Button(self.control_frame, text="Load Directory", command=self.manually_load_directory)
            self.load_directory_button.pack(side=tk.LEFT, padx=10)

            self.prev_button = tk.Button(self.control_frame, text="⏮", font=("Helvetica", 12), command=self.previous_song)
            self.prev_button.pack(side=tk.LEFT, padx=10)

            self.play_pause_button = tk.Button(self.control_frame, text="▶", font=("Helvetica", 12), command=self.play_pause_toggle)
            self.play_pause_button.pack(side=tk.LEFT, padx=10)

            self.next_button = tk.Button(self.control_frame, text="⏭", font=("Helvetica", 12), command=self.next_song)
            self.next_button.pack(side=tk.LEFT, padx=10)

        except Exception as e:
            logging.error(f"Error in create_widgets: {e}")
            traceback.print_exc()

    def drop_files(self, event):
        try:
            directory = event.data.strip('{}')
            if os.path.isdir(directory):
                logging.info(f"Files dropped from directory: {directory}")
                self.load_directory(directory)
            else:
                logging.warning("Dropped item is not a directory")
                messagebox.showerror("Error", "Please drop a directory containing audio files.")
        except Exception as e:
            logging.error(f"Error in drop_files: {e}")
            traceback.print_exc()

    def format_time(self, seconds):
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"

    def track_progress(self):
        while True:
            try:
                if pygame.mixer.music.get_busy() or self.paused:
                    current_pos = pygame.mixer.music.get_pos() / 1000  
                    
                    if self.total_duration > 0:
                        progress_percent = (current_pos / self.total_duration) * 100
                        
                        self.root.after(0, self.update_progress_ui, 
                                        progress_percent, 
                                        self.format_time(current_pos), 
                                        self.format_time(self.total_duration))
                
                time.sleep(0.5)  
            except Exception as e:
                logging.error(f"Error in progress tracking: {e}")
                time.sleep(1)

    def update_progress_ui(self, progress, current_time, total_time):
        if not self.is_seeking:
            self.progress_bar.set(progress)
            self.time_label.config(text=f"{current_time} / {total_time}")

    def on_progress_change(self, value):
        if self.current_song_path and self.total_duration > 0:
            try:
                self.is_seeking = True
                seek_time = (float(value) / 100) * self.total_duration
                pygame.mixer.music.rewind()
                pygame.mixer.music.set_pos(seek_time)
                self.is_seeking = False
            except Exception as e:
                logging.error(f"Error seeking in song: {e}")
                self.is_seeking = False

    def on_volume_change(self, value):
        try:
            volume = float(value) / 100
            pygame.mixer.music.set_volume(volume)
        except Exception as e:
            logging.error(f"Error changing volume: {e}")

    def manually_load_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            logging.info(f"Manually selected directory: {directory}")
            self.load_directory(directory)

    def load_directory(self, directory):
        try:
            self.directory = directory
            songs = self.load_songs()
            
            logging.info(f"Found {len(songs)} songs in directory")
            
            self.song_queue = CircularQueue()
            for song in songs:
                self.song_queue.add(song)
            
            if songs:
                logging.info("Attempting to play first song")
                self.play_song()
                self.store_directory(directory)
            else:
                logging.warning("No songs found in directory")
        except Exception as e:
            logging.error(f"Error loading directory: {e}")
            traceback.print_exc()

    def load_songs(self):
        try:
            songs = [f for f in os.listdir(self.directory) if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac'))]
            logging.info(f"Loaded songs: {songs}")
            return songs
        except Exception as e:
            logging.error(f"Error loading songs: {e}")
            traceback.print_exc()
            return []

    def play_song(self, song=None):
        try:
            if song is None:
                song = self.song_queue.current()
            
            if not song:
                logging.warning("No song to play")
                return

            self.current_song_path = os.path.join(self.directory, song)
            
            pygame.mixer.music.load(self.current_song_path)
            pygame.mixer.music.play()
            
            audio = File(self.current_song_path)
            self.total_duration = audio.info.length
            
            self.paused = False
            self.play_pause_button.config(text="⏸")
            
            self.update_song_info(self.current_song_path)
        except Exception as e:
            logging.error(f"Error playing song: {e}")
            traceback.print_exc()

    def play_pause_toggle(self):
        try:
            if not self.song_queue.queue:
                logging.warning("No songs in queue")
                return

            if self.paused:
                pygame.mixer.music.unpause()
                self.play_pause_button.config(text="⏸")
            else:
                pygame.mixer.music.pause()
                self.play_pause_button.config(text="▶")
            
            self.paused = not self.paused
        except Exception as e:
            logging.error(f"Error in play/pause: {e}")
            traceback.print_exc()

    def next_song(self):
        try:
            next_song = self.song_queue.next()
            logging.info(f"Next song: {next_song}")
            self.play_song(next_song)
        except Exception as e:
            logging.error(f"Error in next_song: {e}")
            traceback.print_exc()

    def previous_song(self):
        try:
            prev_song = self.song_queue.previous()
            logging.info(f"Previous song: {prev_song}")
            self.play_song(prev_song)
        except Exception as e:
            logging.error(f"Error in previous_song: {e}")
            traceback.print_exc()

    def update_song_info(self, song_path):
        try:
            audio = File(song_path, easy=True)
            song_name = os.path.basename(song_path)
            artist = audio.get('artist', ['Unknown'])[0]
            album = audio.get('album', ['Unknown'])[0]
            
            self.song_name_label.config(text=f"Song: {song_name}")
            self.artist_label.config(text=f"Artist: {artist}")
        except Exception as e:
            logging.error(f"Error updating song info: {e}")
            traceback.print_exc()

    def store_directory(self, directory):
        try:
            conn = sqlite3.connect('music_player.db')
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO directories (path) VALUES (?)', (directory,))
            conn.commit()
            conn.close()
            logging.info(f"Stored directory: {directory}")
        except Exception as e:
            logging.error(f"Error storing directory: {e}")

    def load_stored_directories(self):
        try:
            conn = sqlite3.connect('music_player.db')
            cursor = conn.cursor()
            cursor.execute('SELECT path FROM directories')
            rows = cursor.fetchall()
            conn.close()
            
            logging.info(f"Found {len(rows)} stored directories")
            
            if rows:
                directory = rows[0][0]
                logging.info(f"Attempting to load stored directory: {directory}")
                self.load_directory(directory)
        except Exception as e:
            logging.error(f"Error loading stored directories: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    player = MusicPlayer(root)
    root.mainloop()