import os
from yt_dlp import YoutubeDL
from pydub import AudioSegment

def download_and_crop_youtube_audio(video_url, output_filename, start_ms, end_ms):
    # 1. Download the audio from YouTube using yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'outtmpl': 'temp_download.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    print("Downloading audio from YouTube...")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    
    # yt-dlp saves it as temp_download.mp3
    temp_file = "temp_download.mp3"
    
    # 2. Load and crop the audio using pydub
    print(f"Cropping the first {end_ms/1000} seconds...")
    audio = AudioSegment.from_mp3(temp_file)
    cropped_audio = audio[start_ms:end_ms]
    
    # 3. Export the final file to your assets folder
    cropped_audio.export(output_filename, format="mp3")
    print(f"Success! Saved to {output_filename}")
    
    # Clean up the temporary download file
    if os.path.exists(temp_file):
        os.remove(temp_file)

# --- Run the automation ---
youtube_url = "https://www.youtube.com/watch?v=_5bW4NcowVo&list=RD_5bW4NcowVo&start_radio=1"
destination = "drivin_hard_intro.mp3"

# 0 to 15000 milliseconds = first 15 seconds
download_and_crop_youtube_audio(youtube_url, destination, start_ms=0, end_ms=10000)
