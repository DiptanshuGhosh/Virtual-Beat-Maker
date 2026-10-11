import pygame
import json
import os
import wave
import numpy as np
from pygame import mixer

pygame.init()

# ---------------------------------------------------------------------------
# Colors / constants
# ---------------------------------------------------------------------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
DARK_GRAY = (50, 50, 50)
LIGHT_GRAY = (170, 170, 170)
BLUE = (0, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
GOLD = (212, 175, 55)
YELLOW = (255, 230, 90)

WIDTH = 1400
HEIGHT = 800

SAVE_FILE = 'saved_beats.json'
OLD_SAVE_FILE = 'saved_beats.txt'   # only used once, to migrate old data
FLASH_FRAMES = 8                    # how long a cell/meter stays lit after a hit
COUNT_IN_BEATS = 4

INSTRUMENT_NAMES = ['Hi Hat', 'Snare', 'Bass Drum', 'Crash', 'Clap', 'Floor Tom']
INSTRUMENT_KEYS = ['hi_hat', 'snare', 'kick', 'crash', 'clap', 'tom']

# item 3: velocity -> volume mapping. Linear (level/3) made "soft" nearly
# inaudible because loudness perception is logarithmic, not linear -- a drop
# to 33% amplitude reads as a much bigger cut than "33% quieter". These
# floors keep soft hits clearly softer without disappearing.
VELOCITY_VOLUMES = {1: 0.5, 2: 0.75, 3: 1.0}


class DrumMachine:
    def __init__(self):
        self.screen = pygame.display.set_mode([WIDTH, HEIGHT])
        pygame.display.set_caption('The Beat Maker')
        self.label_font = pygame.font.Font('Roboto-Bold.ttf', 32)
        self.medium_font = pygame.font.Font('Roboto-Bold.ttf', 24)
        self.small_font = pygame.font.Font('Roboto-Bold.ttf', 18)
        self.timer = pygame.time.Clock()
        self.fps = 60

        # ---- core state (was: globals) ----
        self.beats = 8
        self.bpm = 240
        self.instruments = len(INSTRUMENT_NAMES)
        self.playing = True
        self.beat_changed = True
        self.active_beat = 0
        self.active_length = 0
        # clicked[row][col]: -1 = off, 1/2/3 = velocity (soft/med/hard)
        self.clicked = [[-1 for _ in range(self.beats)] for _ in range(self.instruments)]
        self.active_list = [1 for _ in range(self.instruments)]

        # ---- new feature state ----
        self.flash_cells = []          # list of [row, col, frames_remaining] -> item 1
        self.meter_levels = [0 for _ in range(self.instruments)]  # item 11
        self.swing_on = False          # item 4
        self.show_help = False         # item 12
        self.counting_in = False       # item 10
        self.count_in_beat = 0
        self.exporting_msg_timer = 0   # item 9, brief on-screen confirmation
        self.export_message = ''

        # ---- item 8: pattern chaining state ----
        self.chain_queue = []          # list of {'name','beats','bpm','clicked'}
        self.chain_active = False      # True while a chain is actually playing
        self.chain_index = 0
        self.chain_loop = False        # replay the whole chain when it finishes

        # ---- menu state ----
        self.save_menu = False
        self.load_menu = False
        self.beat_name = ''
        self.typing = False
        self.index = 100

        # ---- boxes / clickable rects (populated every frame in draw calls) ----
        self.boxes = []
        self.instrument_rects = []

        self._load_sounds()
        pygame.mixer.set_num_channels(self.instruments * 4)
        self.saved_beats = self.load_all_beats()

    # -----------------------------------------------------------------
    # Setup helpers
    # -----------------------------------------------------------------
    def _load_sounds(self):
        self.sounds = {
            'hi_hat': mixer.Sound('sounds\\hi hat.wav'),
            'snare': mixer.Sound('sounds\\snare.wav'),
            'kick': mixer.Sound('sounds\\kick.wav'),
            'crash': mixer.Sound('sounds\\crash.wav'),
            'clap': mixer.Sound('sounds\\clap.wav'),
            'tom': mixer.Sound('sounds\\tom.wav'),
        }
        # short high blip for the count-in metronome (item 10).
        # Falls back to the hi-hat sample if you don't have a dedicated click.wav.
        try:
            self.click_sound = mixer.Sound('sounds\\click.wav')
        except (pygame.error, FileNotFoundError):
            self.click_sound = self.sounds['hi_hat']

    # -----------------------------------------------------------------
    # Save / load  -> item 5 (JSON instead of hand-parsed text)
    # -----------------------------------------------------------------
    def load_all_beats(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return []
        if os.path.exists(OLD_SAVE_FILE):
            # one-time migration from your old hand-parsed .txt format
            migrated = self._migrate_old_format()
            self.save_all_beats(migrated)
            return migrated
        return []

    def _migrate_old_format(self):
        migrated = []
        with open(OLD_SAVE_FILE, 'r') as f:
            raw_lines = [line for line in f if line.strip()]
        for entry in raw_lines:
            try:
                name_start = entry.index('name: ') + 6
                name_end = entry.index(', beats:')
                name = entry[name_start:name_end]
                beats_end = entry.index(', bpm:')
                beats_val = int(entry[name_end + 8:beats_end])
                bpm_end = entry.index(', selected:')
                bpm_val = int(entry[beats_end + 6:bpm_end])
                clicks_string = entry[bpm_end + 14:-1].strip()
                clicks_rows = clicks_string.strip('[]').split('], [')
                clicked = []
                for row in clicks_rows:
                    clicked.append([int(x) for x in row.split(', ')])
                migrated.append({'name': name, 'beats': beats_val, 'bpm': bpm_val, 'clicked': clicked})
            except (ValueError, IndexError):
                continue  # skip anything that doesn't parse cleanly
        return migrated

    def save_all_beats(self, beats_list=None):
        with open(SAVE_FILE, 'w') as f:
            json.dump(beats_list if beats_list is not None else self.saved_beats, f, indent=2)

    @staticmethod
    def _sanitize_grid(grid):
        # repairs patterns saved with the old velocity-cycling bug, where a
        # single click produced level 0 (looked soft, played nothing).
        # 0 -> 1 (treat as the softest real level); anything else passes through.
        return [[1 if cell == 0 else cell for cell in row] for row in grid]

    # -----------------------------------------------------------------
    # Drawing
    # -----------------------------------------------------------------
    def draw_grid(self):
        boxes = []
        pygame.draw.rect(self.screen, GRAY, [0, 0, 200, HEIGHT - 200], 5)
        pygame.draw.rect(self.screen, GRAY, [0, HEIGHT - 200, WIDTH, 200], 5)
        for i in range(self.instruments + 1):
            pygame.draw.line(self.screen, GRAY, (0, i * 100), (200, i * 100), 3)

        colors = [GRAY, WHITE, GRAY]
        for row, name in enumerate(INSTRUMENT_NAMES):
            label = self.label_font.render(name, True, colors[self.active_list[row]])
            self.screen.blit(label, (30, row * 100 + 30))
            # item 11: level meter bar under each instrument label
            meter_w = int((self.meter_levels[row] / FLASH_FRAMES) * 150)
            if meter_w > 0:
                pygame.draw.rect(self.screen, GREEN, [30, row * 100 + 70, meter_w, 10])

        cell_w = (WIDTH - 200) // self.beats
        for i in range(self.beats):
            for j in range(self.instruments):
                level = self.clicked[j][i]
                is_flashing = any(fc[0] == j and fc[1] == i for fc in self.flash_cells)
                if level == -1:
                    color = GRAY
                elif is_flashing:
                    color = WHITE                                   # item 1
                elif self.active_list[j] == 1:
                    shade = int(70 + level * 60)                    # item 3: velocity shading
                    color = (0, min(shade, 255), 0)
                else:
                    color = DARK_GRAY

                rect = pygame.draw.rect(
                    self.screen, color,
                    [i * cell_w + 205, (j * 100) + 5, cell_w - 10, 90], 0, 3)
                pygame.draw.rect(self.screen, GOLD, [i * cell_w + 200, j * 100, cell_w, 100], 5, 5)
                pygame.draw.rect(self.screen, BLACK, [i * cell_w + 200, j * 100, cell_w, 100], 2, 5)
                boxes.append((rect, (i, j)))

        pygame.draw.rect(
            self.screen, BLUE,
            [self.active_beat * cell_w + 200, 0, cell_w, self.instruments * 100], 5, 3)
        return boxes

    def draw_bottom_bar(self):
        s = self.screen
        play_pause = pygame.draw.rect(s, GRAY, [50, HEIGHT - 150, 200, 100], 0, 5)
        s.blit(self.label_font.render('Play/Pause', True, WHITE), (70, HEIGHT - 130))
        if self.counting_in:
            status = 'Count-in...'
        elif self.playing:
            status = 'Playing'
        else:
            status = 'Paused'
        s.blit(self.medium_font.render(status, True, DARK_GRAY), (70, HEIGHT - 100))

        bpm_rect = pygame.draw.rect(s, GRAY, [300, HEIGHT - 150, 200, 100], 5, 5)
        s.blit(self.medium_font.render('Beats Per Minute', True, WHITE), (308, HEIGHT - 130))
        s.blit(self.label_font.render(f'{self.bpm}', True, WHITE), (370, HEIGHT - 100))
        bpm_add_rect = pygame.draw.rect(s, GRAY, [510, HEIGHT - 150, 48, 48], 0, 5)
        bpm_sub_rect = pygame.draw.rect(s, GRAY, [510, HEIGHT - 100, 48, 48], 0, 5)
        s.blit(self.medium_font.render('+5', True, WHITE), (520, HEIGHT - 140))
        s.blit(self.medium_font.render('-5', True, WHITE), (520, HEIGHT - 90))

        beats_rect = pygame.draw.rect(s, GRAY, [600, HEIGHT - 150, 200, 100], 5, 5)
        s.blit(self.medium_font.render('Beats In Loop', True, WHITE), (612, HEIGHT - 130))
        s.blit(self.label_font.render(f'{self.beats}', True, WHITE), (670, HEIGHT - 100))
        beats_add_rect = pygame.draw.rect(s, GRAY, [810, HEIGHT - 150, 48, 48], 0, 5)
        beats_sub_rect = pygame.draw.rect(s, GRAY, [810, HEIGHT - 100, 48, 48], 0, 5)
        s.blit(self.medium_font.render('+1', True, WHITE), (820, HEIGHT - 140))
        s.blit(self.medium_font.render('-1', True, WHITE), (820, HEIGHT - 90))

        # item 4: swing toggle button, tucked next to BPM controls
        swing_rect = pygame.draw.rect(s, GREEN if self.swing_on else GRAY, [570, HEIGHT - 150, 20, 100], 0, 3)

        clear_rect = pygame.draw.rect(s, GRAY, [1150, HEIGHT - 150, 200, 100], 0, 5)
        s.blit(self.label_font.render('Clear Board', True, WHITE), (1160, HEIGHT - 130))

        save_button = pygame.draw.rect(s, GRAY, [900, HEIGHT - 150, 200, 48], 0, 5)
        s.blit(self.label_font.render('Save Beat', True, WHITE), (920, HEIGHT - 140))
        load_button = pygame.draw.rect(s, GRAY, [900, HEIGHT - 98, 200, 48], 0, 5)
        s.blit(self.label_font.render('Load Beat', True, WHITE), (920, HEIGHT - 90))

        # item 9: export button (WAV only)
        export_button = pygame.draw.rect(s, GRAY, [1150, HEIGHT - 98, 200, 48], 0, 5)
        s.blit(self.medium_font.render('Export WAV (W)', True, WHITE), (1165, HEIGHT - 90))

        # item 8: chain status, shown when a chain is queued or playing
        if self.chain_active:
            current_name = self.chain_queue[self.chain_index]['name'] if self.chain_queue else ''
            chain_text = f'Chain: {self.chain_index + 1}/{len(self.chain_queue)} - {current_name}'
            s.blit(self.small_font.render(chain_text, True, YELLOW), (210, HEIGHT - 195))
        elif self.chain_queue:
            s.blit(self.small_font.render(
                f'Chain queued: {len(self.chain_queue)} pattern(s) - open Load menu to play',
                True, GRAY), (210, HEIGHT - 195))

        if self.exporting_msg_timer > 0:
            msg = self.medium_font.render(self.export_message, True, YELLOW)
            s.blit(msg, (900, HEIGHT - 180))
            self.exporting_msg_timer -= 1

        return {
            'play_pause': play_pause, 'bpm_add': bpm_add_rect, 'bpm_sub': bpm_sub_rect,
            'beats_add': beats_add_rect, 'beats_sub': beats_sub_rect, 'clear': clear_rect,
            'save_button': save_button, 'load_button': load_button, 'swing': swing_rect,
            'export_button': export_button,
        }

    def draw_save_menu(self):
        s = self.screen
        pygame.draw.rect(s, BLACK, [0, 0, WIDTH, HEIGHT])
        s.blit(self.label_font.render('SAVE MENU: Enter a Name for this beat', True, WHITE), (400, 40))
        exit_btn = pygame.draw.rect(s, GRAY, [WIDTH - 200, HEIGHT - 100, 180, 90], 0, 5)
        s.blit(self.label_font.render('Close', True, WHITE), (WIDTH - 160, HEIGHT - 70))
        saving_btn = pygame.draw.rect(s, GRAY, [WIDTH // 2 - 100, HEIGHT * 0.75, 200, 100], 0, 5)
        s.blit(self.label_font.render('Save Beat', True, WHITE), (WIDTH // 2 - 70, HEIGHT * 0.75 + 30))
        if self.typing:
            pygame.draw.rect(s, DARK_GRAY, [400, 200, 600, 200], 0, 5)
        entry_rect = pygame.draw.rect(s, GRAY, [400, 200, 600, 200], 5, 5)
        s.blit(self.label_font.render(f'{self.beat_name}', True, WHITE), (430, 250))
        return exit_btn, saving_btn, entry_rect

    def draw_load_menu(self):
        loaded_beats, loaded_bpm, loaded_clicked = 0, 0, []
        s = self.screen
        pygame.draw.rect(s, BLACK, [0, 0, WIDTH, HEIGHT])
        s.blit(self.label_font.render('LOAD MENU: Select a beat to load in', True, WHITE), (400, 40))
        exit_btn = pygame.draw.rect(s, GRAY, [WIDTH - 200, HEIGHT - 100, 180, 90], 0, 5)
        s.blit(self.label_font.render('Close', True, WHITE), (WIDTH - 160, HEIGHT - 70))
        loading_btn = pygame.draw.rect(s, GRAY, [WIDTH // 2 - 250, HEIGHT * 0.87, 200, 100], 0, 5)
        s.blit(self.label_font.render('Load Beat', True, WHITE), (WIDTH // 2 - 220, HEIGHT * 0.87 + 30))
        delete_btn = pygame.draw.rect(s, GRAY, [WIDTH // 2 - 480, HEIGHT * 0.87, 200, 100], 0, 5)
        s.blit(self.label_font.render('Delete Beat', True, WHITE), (WIDTH // 2 - 465, HEIGHT * 0.87 + 30))
        # item 8: add the currently selected saved beat to the chain queue
        add_chain_btn = pygame.draw.rect(s, GRAY, [WIDTH // 2 + 20, HEIGHT * 0.87, 220, 100], 0, 5)
        s.blit(self.medium_font.render('Add to Chain', True, WHITE), (WIDTH // 2 + 40, HEIGHT * 0.87 + 35))

        if 0 <= self.index < len(self.saved_beats):
            pygame.draw.rect(s, LIGHT_GRAY, [190, 100 + self.index * 50, 800, 50])

        for beat in range(min(len(self.saved_beats), 10)):
            entry = self.saved_beats[beat]
            row_text = self.medium_font.render(f'{beat + 1}', True, WHITE)
            s.blit(row_text, (200, 100 + beat * 50))
            name_text = self.medium_font.render(entry['name'], True, WHITE)
            s.blit(name_text, (240, 100 + beat * 50))
            if beat == self.index:
                loaded_beats = entry['beats']
                loaded_bpm = entry['bpm']
                loaded_clicked = self._sanitize_grid(entry['clicked'])

        loaded_info = [loaded_beats, loaded_bpm, loaded_clicked]
        entry_rect = pygame.draw.rect(s, GRAY, [190, 90, 800, 600], 5, 5)

        # item 8: chain queue panel, right-hand side
        pygame.draw.rect(s, GRAY, [1010, 90, 380, 600], 5, 5)
        s.blit(self.medium_font.render('CHAIN QUEUE', True, YELLOW), (1030, 100))
        for i, entry in enumerate(self.chain_queue[:12]):
            marker = '> ' if (self.chain_active and i == self.chain_index) else f'{i + 1}. '
            line = self.small_font.render(f'{marker}{entry["name"]}', True, WHITE)
            s.blit(line, (1030, 145 + i * 30))
        play_chain_btn = pygame.draw.rect(s, GREEN if self.chain_queue else DARK_GRAY,
                                           [1030, 560, 160, 60], 0, 5)
        s.blit(self.medium_font.render('Play Chain', True, BLACK), (1045, 578))
        clear_chain_btn = pygame.draw.rect(s, GRAY, [1210, 560, 160, 60], 0, 5)
        s.blit(self.medium_font.render('Clear Chain', True, WHITE), (1220, 578))

        return (exit_btn, loading_btn, entry_rect, delete_btn, loaded_info,
                add_chain_btn, play_chain_btn, clear_chain_btn)

    def draw_help_overlay(self):
        # item 12
        overlay = pygame.Surface((WIDTH, HEIGHT))
        overlay.set_alpha(215)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))
        lines = [
            'H              toggle this help',
            'SPACE          play / pause',
            'UP / DOWN      BPM +5 / -5',
            'Left click     cycle cell velocity (off -> soft -> med -> hard)',
            'Right click    clear a cell',
            'Ctrl+S         open save menu',
            'Ctrl+L         open load menu',
            'W              export current pattern to WAV',
            '(Load menu)    Add to Chain / Play Chain / Clear Chain',
        ]
        title = self.label_font.render('CONTROLS', True, YELLOW)
        self.screen.blit(title, (100, 80))
        for idx, line in enumerate(lines):
            txt = self.medium_font.render(line, True, WHITE)
            self.screen.blit(txt, (100, 150 + idx * 40))

    # -----------------------------------------------------------------
    # Audio
    # -----------------------------------------------------------------
    def play_notes(self):
        for row in range(self.instruments):
            level = self.clicked[row][self.active_beat]
            if level > 0 and self.active_list[row] == 1:
                sound = self.sounds[INSTRUMENT_KEYS[row]]
                sound.set_volume(VELOCITY_VOLUMES[level])          # item 3
                sound.play()
                self.flash_cells.append([row, self.active_beat, FLASH_FRAMES])  # item 1
                self.meter_levels[row] = FLASH_FRAMES              # item 11

    def _decay_flash_and_meters(self):
        for fc in self.flash_cells[:]:
            fc[2] -= 1
            if fc[2] <= 0:
                self.flash_cells.remove(fc)
        for row in range(self.instruments):
            if self.meter_levels[row] > 0:
                self.meter_levels[row] -= 1

    # -----------------------------------------------------------------
    # item 9: export the current pattern to a mixed-down WAV file
    # -----------------------------------------------------------------
    def export_wav(self, filename='beat_export.wav'):
        mixer_info = pygame.mixer.get_init()
        if mixer_info is None:
            return
        freq, fmt, channels = mixer_info
        beat_length_ticks = 3600 // self.bpm          # game ticks (60fps) per beat
        seconds_per_beat = beat_length_ticks / self.fps
        samples_per_beat = int(freq * seconds_per_beat)
        total_samples = samples_per_beat * self.beats

        mix_buffer = np.zeros((total_samples, channels), dtype=np.int32)

        for i in range(self.beats):
            offset = i * samples_per_beat
            for row in range(self.instruments):
                level = self.clicked[row][i]
                if level <= 0 or self.active_list[row] != 1:
                    continue
                raw = self.sounds[INSTRUMENT_KEYS[row]].get_raw()
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.int32)
                if channels == 2 and samples.ndim == 1:
                    samples = samples.reshape(-1, 2)
                elif channels == 1:
                    samples = samples.reshape(-1, 1)
                samples = (samples * VELOCITY_VOLUMES[level]).astype(np.int32)
                end = min(offset + len(samples), total_samples)
                length = end - offset
                if length > 0:
                    mix_buffer[offset:end] += samples[:length]

        mix_buffer = np.clip(mix_buffer, -32768, 32767).astype(np.int16)

        with wave.open(filename, 'w') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(freq)
            wf.writeframes(mix_buffer.tobytes())

        self.exporting_msg_timer = 120  # ~2 seconds at 60fps
        self.export_message = f'Exported to {filename}'

    # -----------------------------------------------------------------
    # item 8: pattern chaining
    # -----------------------------------------------------------------
    def start_chain(self):
        if not self.chain_queue:
            return
        self.chain_active = True
        self.chain_index = 0
        self._load_chain_pattern(0)
        self.active_beat = 0
        self.active_length = 0
        self.playing = True

    def clear_chain(self):
        self.chain_queue = []
        self.chain_active = False
        self.chain_index = 0

    def _load_chain_pattern(self, index):
        entry = self.chain_queue[index]
        self.beats = entry['beats']
        self.bpm = entry['bpm']
        self.clicked = self._sanitize_grid([row[:] for row in entry['clicked']])

    def _advance_chain(self):
        self.chain_index += 1
        if self.chain_index >= len(self.chain_queue):
            if self.chain_loop:
                self.chain_index = 0
            else:
                self.chain_active = False
                self.playing = False
                return
        self._load_chain_pattern(self.chain_index)

    # -----------------------------------------------------------------
    # Event handling
    # -----------------------------------------------------------------
    def handle_events(self, bottom_rects):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                self._handle_keydown(event)

            if event.type == pygame.TEXTINPUT and self.typing:
                self.beat_name += event.text

            if event.type == pygame.MOUSEBUTTONDOWN and not self.save_menu and not self.load_menu:
                self._handle_mouse_down(event)

            if event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event, bottom_rects)

        return True

    def _handle_keydown(self, event):
        mods = pygame.key.get_mods()
        if event.key == pygame.K_h:
            self.show_help = not self.show_help                          # item 12
        elif event.key == pygame.K_BACKSPACE and len(self.beat_name) > 0:
            self.beat_name = self.beat_name[:-1]
        elif self.save_menu or self.load_menu:
            return  # don't fire shortcuts while a menu is open
        elif event.key == pygame.K_SPACE:                                # item 3 (roadmap)
            self._toggle_play()
        elif event.key == pygame.K_UP:
            self.bpm += 5
        elif event.key == pygame.K_DOWN:
            self.bpm -= 5
        elif event.key == pygame.K_s and mods & pygame.KMOD_CTRL:
            self.save_menu = True
            self.playing = False
        elif event.key == pygame.K_l and mods & pygame.KMOD_CTRL:
            self.load_menu = True
            self.playing = False
        elif event.key == pygame.K_w:
            self.export_wav()                                            # item 9

    def _toggle_play(self):
        if self.counting_in:
            return
        if self.playing:
            self.playing = False
        else:
            self.counting_in = True                                      # item 10
            self.count_in_beat = 0
            self.active_length = 0

    def _handle_mouse_down(self, event):
        for rect, (col, row) in self.boxes:
            if rect.collidepoint(event.pos):
                if event.button == 1:      # left click: cycle velocity   # item 3
                    current = self.clicked[row][col]
                    if current == -1:
                        self.clicked[row][col] = 1        # off -> soft (first click)
                    elif current < 3:
                        self.clicked[row][col] = current + 1
                    else:
                        self.clicked[row][col] = -1        # hard -> off
                elif event.button == 3:    # right click: clear
                    self.clicked[row][col] = -1
                return

    def _handle_mouse_up(self, event, r):
        if self.save_menu:
            self._handle_save_menu_click(event)
            return
        if self.load_menu:
            self._handle_load_menu_click(event)
            return

        if r['play_pause'].collidepoint(event.pos):
            self._toggle_play()
        if r['beats_add'].collidepoint(event.pos):
            self.beats += 1
            for row in self.clicked:
                row.append(-1)
        elif r['beats_sub'].collidepoint(event.pos) and self.beats > 1:
            self.beats -= 1
            for row in self.clicked:
                row.pop(-1)
            if self.active_beat >= self.beats:
                self.active_beat = 0
        if r['bpm_add'].collidepoint(event.pos):
            self.bpm += 5
        elif r['bpm_sub'].collidepoint(event.pos) and self.bpm > 5:
            self.bpm -= 5
        if r['swing'].collidepoint(event.pos):                            # item 4
            self.swing_on = not self.swing_on
        if r['clear'].collidepoint(event.pos):
            self.clicked = [[-1 for _ in range(self.beats)] for _ in range(self.instruments)]
        for i, rect in enumerate(self.instrument_rects):
            if rect.collidepoint(event.pos):
                self.active_list[i] *= -1
        if r['save_button'].collidepoint(event.pos):
            self.save_menu = True
            self.playing = False
        if r['load_button'].collidepoint(event.pos):
            self.load_menu = True
            self.playing = False
        if r['export_button'].collidepoint(event.pos):                   # item 9
            self.export_wav()

    def _handle_save_menu_click(self, event):
        if self._exit_btn.collidepoint(event.pos):
            self._close_menus()
            return
        if self._entry_rect.collidepoint(event.pos):
            self.typing = not self.typing
            return
        if self._saving_btn.collidepoint(event.pos) and self.beat_name.strip():
            self.saved_beats.append({
                'name': self.beat_name, 'beats': self.beats,
                'bpm': self.bpm, 'clicked': self.clicked,
            })
            self.save_all_beats()                                        # item 5
            self._close_menus()

    def _handle_load_menu_click(self, event):
        if self._exit_btn.collidepoint(event.pos):
            self._close_menus()
            return
        if self._entry_rect.collidepoint(event.pos):
            self.index = (event.pos[1] - 100) // 50
            return
        if self._delete_btn.collidepoint(event.pos):
            if 0 <= self.index < len(self.saved_beats):
                self.saved_beats.pop(self.index)
                self.save_all_beats()
            return
        if self._loading_btn.collidepoint(event.pos):
            if 0 <= self.index < len(self.saved_beats):
                entry = self.saved_beats[self.index]
                self.beats = entry['beats']
                self.bpm = entry['bpm']
                self.clicked = self._sanitize_grid(entry['clicked'])
                self.index = 100
                self._close_menus()
            return
        if self._add_chain_btn.collidepoint(event.pos):                  # item 8
            if 0 <= self.index < len(self.saved_beats):
                entry = self.saved_beats[self.index]
                self.chain_queue.append({
                    'name': entry['name'], 'beats': entry['beats'],
                    'bpm': entry['bpm'], 'clicked': [row[:] for row in entry['clicked']],
                })
            return
        if self._play_chain_btn.collidepoint(event.pos):                 # item 8
            self.start_chain()
            self._close_menus()
            return
        if self._clear_chain_btn.collidepoint(event.pos):                # item 8
            self.clear_chain()
            return

    def _close_menus(self):
        self.save_menu = False
        self.load_menu = False
        self.playing = True
        self.typing = False
        self.beat_name = ''

    # -----------------------------------------------------------------
    # Update / timing  -> item 4 (swing) + item 10 (count-in)
    # -----------------------------------------------------------------
    def update_timing(self):
        beat_length = 3600 // self.bpm
        if self.swing_on and self.active_beat % 2 == 1:
            beat_length += beat_length // 6

        if self.counting_in:
            if self.active_length < beat_length:
                self.active_length += 1
            else:
                self.active_length = 0
                self.click_sound.play()
                self.count_in_beat += 1
                if self.count_in_beat >= COUNT_IN_BEATS:
                    self.counting_in = False
                    self.playing = True
                    self.active_beat = 0
                    self.beat_changed = True
        elif self.playing:
            if self.active_length < beat_length:
                self.active_length += 1
            else:
                self.active_length = 0
                if self.active_beat < self.beats - 1:
                    self.active_beat += 1
                else:
                    self.active_beat = 0
                    if self.chain_active:                                 # item 8
                        self._advance_chain()
                self.beat_changed = True

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------
    def run(self):
        running = True
        while running:
            self.timer.tick(self.fps)
            self.screen.fill(BLACK)

            self.boxes = self.draw_grid()
            bottom_rects = self.draw_bottom_bar()

            self.instrument_rects = [
                pygame.rect.Rect((0, i * 100), (200, 100)) for i in range(self.instruments)
            ]

            if self.beat_changed:
                self.play_notes()
                self.beat_changed = False
            self._decay_flash_and_meters()

            if self.save_menu:
                self._exit_btn, self._saving_btn, self._entry_rect = self.draw_save_menu()
            elif self.load_menu:
                (self._exit_btn, self._loading_btn, self._entry_rect,
                 self._delete_btn, self._loaded_info,
                 self._add_chain_btn, self._play_chain_btn,
                 self._clear_chain_btn) = self.draw_load_menu()
            elif self.show_help:
                self.draw_help_overlay()

            running = self.handle_events(bottom_rects)
            self.update_timing()

            pygame.display.flip()

        self.save_all_beats()
        pygame.quit()


if __name__ == '__main__':
    DrumMachine().run()