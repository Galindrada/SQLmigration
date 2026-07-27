import os
import yt_dlp

# Target destination folder matching your layout
MUSIC_FOLDER = "assets/music"

def download_youtube_audio(youtube_url):
    # Ensure the destination folder exists side-by-side
    if not os.path.exists(MUSIC_FOLDER):
        os.makedirs(MUSIC_FOLDER)
        print(f"Created music directory at: {MUSIC_FOLDER}")

    # Configuration for extracting pure high-quality audio
    ydl_opts = {
        'format': 'bestaudio/best',  # Grab the highest quality audio stream available
        'outtmpl': os.path.join(MUSIC_FOLDER, '%(title)s.%(ext)s'), # Save directly into your music folder
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',  # Convert stream to a standard mp3 file
            'preferredquality': '192', # Crisp 192kbps quality
        }],
    }

    print(f"Connecting to YouTube to fetch: {youtube_url}...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        print("\n🎵 Successfully downloaded and converted to MP3!")
        print(f"Check your '{MUSIC_FOLDER}' folder for the new tune.")
    except Exception as e:
        print(f"\n❌ An error occurred during download: {e}")

if __name__ == "__main__":
    # Paste your YouTube link here
    url_input = input("Enter YouTube Video URL: ").strip()
    
    if url_input:
        download_youtube_audio(url_input)
    else:
        print("URL cannot be empty.")