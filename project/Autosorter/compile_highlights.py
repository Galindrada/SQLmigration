import os
import random
import sys

# 🔥 CRITICAL FIX: Patch the Pillow ANTIALIAS bug before importing MoviePy
try:
    import PIL.Image
    if not hasattr(PIL.Image, 'ANTIALIAS'):
        # Map the old name to the modern modern resampling attribute
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
except ImportError:
    pass

# Now safe to import MoviePy components
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
import moviepy.video.fx as vfx

# --- ROBUST CROSS-VERSION AUDIO IMPORT ---
try:
    from moviepy.audio.compositing.concatenate import concatenate_audioclips
except ModuleNotFoundError:
    try:
        from moviepy.audio.audio_clips import concatenate_audioclips
    except ModuleNotFoundError:
        from moviepy.editor import concatenate_audioclips

# --- CONFIGURATION ---
VIDEOS_FOLDER = "./highlights"
MUSIC_FOLDER = "./music"
OUTPUT_PATH = "pes6_ultimate_compilation.mp4"
TARGET_RESOLUTION = (1280, 720)  
TRANSITION_DURATION = 0.5  
FADE_DURATION = 0.4        

def apply_random_effects(clip):
    """Applies a random fun visual effect to a clip to spice it up."""
    def apply_fx(c, fx_class, fx_func_name, *args, **kwargs):
        if hasattr(c, "with_effects"):
            return c.with_effects([fx_class(*args, **kwargs)])
        elif hasattr(c, "fx") and hasattr(vfx, fx_func_name):
            return c.fx(getattr(vfx, fx_func_name), *args, **kwargs)
        return c

    effects = [
        lambda c: c,  
        lambda c: apply_fx(c, getattr(vfx, 'Colorx', None), 'colorx', 1.3),      
        lambda c: apply_fx(c, getattr(vfx, 'MirrorX', None), 'mirror_x'),       
        lambda c: apply_fx(c, getattr(vfx, 'BlackWhite', None), 'blackwhite')   
    ]
    
    if random.random() < 0.4:
        effect = random.choice(effects[1:])
        print(f"✨ Applying random effect to a segment...")
        return effect(clip)
    return clip

def apply_retro_fades(clip, duration):
    """Explicitly applies retro fade-in and fade-out transitions to the video."""
    if hasattr(clip, "with_effects"):
        return clip.with_effects([vfx.FadeIn(duration), vfx.FadeOut(duration)])
    elif hasattr(clip, "fadein") and hasattr(clip, "fadeout"):
        return clip.fadein(duration).fadeout(duration)
    return clip

def resize_clip(clip, target_res):
    """Safely resizes the clip supporting both older and newer MoviePy versions."""
    if hasattr(clip, "with_effects"):
        if hasattr(vfx, 'Resize'):
            return clip.with_effects([vfx.Resize(target_res)])
        elif hasattr(vfx, 'Resized'):
            return clip.with_effects([vfx.Resized(target_res)])
    
    if hasattr(clip, "resize"):
        return clip.resize(target_res)
    elif hasattr(clip, "target_resolution"):
        return clip.target_resolution(target_res)
        
    return clip

def mute_clip(clip):
    """Safely removes the original audio across all MoviePy versions."""
    if hasattr(clip, "without_audio"):
        return clip.without_audio()
    elif hasattr(clip, "with_audio"):
        return clip.with_audio(None)
    elif hasattr(clip, "set_audio"):
        return clip.set_audio(None)
    return clip

def build_music_playlist(music_files, target_duration):
    """Selects and sequences multiple songs to seamlessly cover the video length."""
    chosen_tracks = []
    current_total_duration = 0
    
    pool = music_files.copy()
    random.shuffle(pool)
    
    while current_total_duration < target_duration:
        if not pool:
            pool = music_files.copy()
            random.shuffle(pool)
            
        track_path = pool.pop(0)
        audio_clip = AudioFileClip(track_path)
        chosen_tracks.append(audio_clip)
        current_total_duration += audio_clip.duration
        
        print(f"🎵 Queued background track: {os.path.basename(track_path)}")
        
    full_soundtrack = concatenate_audioclips(chosen_tracks)
    
    if full_soundtrack.duration > target_duration:
        if hasattr(full_soundtrack, 'with_section'):
            full_soundtrack = full_soundtrack.with_section(0, target_duration)
        elif hasattr(full_soundtrack, 'subclip'):
            full_soundtrack = full_soundtrack.subclip(0, target_duration)
            
    return full_soundtrack

def main():
    os.makedirs(VIDEOS_FOLDER, exist_ok=True)
    os.makedirs(MUSIC_FOLDER, exist_ok=True)

    video_extensions = ('.mp4', '.avi', '.mkv', '.mov')
    video_files = sorted([os.path.join(VIDEOS_FOLDER, f) for f in os.listdir(VIDEOS_FOLDER) if f.lower().endswith(video_extensions)])
    
    audio_extensions = ('.mp3', '.wav', '.m4a')
    music_files = sorted([os.path.join(MUSIC_FOLDER, f) for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith(audio_extensions)])

    if not video_files:
        print(f"❌ No videos found in '{VIDEOS_FOLDER}'. Please add some clips and rerun!")
        return

    print(f"🎬 Found {len(video_files)} videos. Processing...")

    clips = []
    for path in video_files:
        try:
            clip = VideoFileClip(path)
            clip = mute_clip(clip)
            clip = resize_clip(clip, TARGET_RESOLUTION)
            clip = apply_random_effects(clip)
            clip = apply_retro_fades(clip, FADE_DURATION)
            clips.append(clip)
        except Exception as e:
            print(f"⚠️ Skipping file {path}: {e}")

    if not clips:
        print("❌ No videos were successfully processed.")
        return

    print("🔄 Stitching clips together with transitions...")
    final_video = concatenate_videoclips(clips, method="compose", padding=-TRANSITION_DURATION)

    if music_files:
        print(f"🎶 Calculating background music needs for {final_video.duration:.2f} seconds...")
        bg_audio = build_music_playlist(music_files, final_video.duration)

        if hasattr(final_video, 'with_audio'):
            final_video = final_video.with_audio(bg_audio)
        elif hasattr(final_video, 'set_audio'):
            final_video = final_video.set_audio(bg_audio)
    else:
        print("⚠️ No music found in folder. Outputting silent compilation.")

    print(f"🚀 Rendering final video to {OUTPUT_PATH}...")
    final_video.write_videofile(
        OUTPUT_PATH,
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

    for clip in clips:
        clip.close()
    final_video.close()
    print("✅ Done!")

if __name__ == "__main__":
    main()
