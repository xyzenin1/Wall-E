import discord
import time
from discord.ext import commands
import os
import asyncio
import yt_dlp
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
import urllib.parse, urllib.request, re
import random

from urllib import parse, request
import json

import subprocess
import io
import sys

if sys.platform == 'win32':
    import subprocess as _subprocess_module
    _original_popen_class = _subprocess_module.Popen
    
    class PatchedPopen(_original_popen_class):
        def __init__(self, *args, **kwargs):
            # Remove the problematic Windows flag
            if 'creationflags' in kwargs:
                print(f"Removing creationflags: {kwargs['creationflags']}")
                del kwargs['creationflags']
            super().__init__(*args, **kwargs)
    
    # Replace in the module itself
    _subprocess_module.Popen = PatchedPopen
    
    # Also replace subprocess.Popen global reference
    subprocess.Popen = PatchedPopen
    
    print("✓ Applied Windows subprocess patch globally")
    
    

def run_bot():
    load_dotenv()
    #discord token
    TOKEN = os.getenv('discord_token')
    #spotify tokens
    SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
    SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix="!", intents=intents, help_command=None)


    queues = {}
    history = {}
    voice_clients = {}
    youtube_base_url = 'https://www.youtube.com/'
    youtube_results_url = youtube_base_url + 'results?'
    youtube_watch_url = youtube_base_url + 'watch?v='

    yt_dl_options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
        "cachedir": False,
        "no_cache_dir": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "format_sort": ["proto:https"],
    }
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    
    #Initialize spotify API
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
        
        ))
    
    ffmpeg_path = None
    
    try:
        # Try to find FFmpeg in the PATH
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
        
        if not ffmpeg_path:
            # Try common FFmpeg locations
            common_paths = [
                'C:\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
            ]
            for path in common_paths:
                if os.path.exists(path):
                    ffmpeg_path = path
                    print(f"✅ Found FFmpeg at: {ffmpeg_path}")
                    break
        else:
            print(f"✅ Found FFmpeg in PATH at: {ffmpeg_path}")
        
        if not ffmpeg_path:
            print("❌ WARNING: FFmpeg not found! Please install FFmpeg and add it to PATH.")
            print("Download from: https://ffmpeg.org/download.html")
        else:
            # Set the FFmpeg executable for discord.py
            discord.FFmpegOpusAudio.executable = ffmpeg_path
            discord.FFmpegPCMAudio.executable = ffmpeg_path
            os.environ['FFMPEG_EXECUTABLE'] = ffmpeg_path
            print(f"✅ Discord.py configured to use FFmpeg at: {ffmpeg_path}")
            
    except Exception as e:
        print(f"❌ Error detecting FFmpeg: {e}")
    
    
    # Configure FFmpeg options
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -filter:a "volume=0.25"'
    }
    
    # Set executable path if found
    if ffmpeg_path:
        discord.FFmpegOpusAudio.executable = ffmpeg_path
        discord.FFmpegPCMAudio.executable = ffmpeg_path

    @client.event
    async def on_ready():
        print(f'{client.user} is booting up!')
        

    async def play_next(ctx):
        if ctx.guild.id in queues and queues[ctx.guild.id] != []:
            link = queues[ctx.guild.id].pop(0)
            history.setdefault(ctx.guild.id, []).append(link)
            
            # Re-extract info to get fresh URL
            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
                song_url = data['url']
                
                http_headers = data.get('http_headers', {})
                player = await create_player(song_url, http_headers)
                
                if player:
                    voice_clients[ctx.guild.id].play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            except Exception as e:
                print(f"Error in play_next: {e}")
                # Try next song if this one fails
                await play_next(ctx)
            
   
    async def create_player(song_url, http_headers=None):
        """Create audio player with proper error handling"""
        try:
            print(f"\n=== Creating Player ===")
            print(f"URL: {song_url[:80]}...")
            
            # Build FFmpeg options with headers if available
            before_options = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
            
            # Add headers if provided (helps with some videos)
            if http_headers:
                user_agent = http_headers.get('User-Agent', '')
                if user_agent:
                    before_options += f' -user_agent "{user_agent}"'
            
            player = discord.FFmpegPCMAudio(
                song_url,
                executable=ffmpeg_path,
                before_options=before_options,
                options='-vn'
            )
            
            # Apply volume control (0.5 = 50% volume)
            player = discord.PCMVolumeTransformer(player, volume=0.5)
        
            print("✓ Created player with volume control")
            return player
            
        except Exception as e:
            print(f"✗ Player creation error: {e}")
            import traceback
            traceback.print_exc()
            return None

    
    # Helper function to get YouTube link from search query
    async def get_youtube_link(query):
        try:
            query_string = urllib.parse.urlencode({
                'search_query': query
            })

            content = urllib.request.urlopen(
                youtube_results_url + query_string
            )

            search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
            
            if not search_results:
                return None

            return youtube_watch_url + search_results[0]
        except Exception as e:
            print(f"Error searching YouTube: {e}")
            return None
            
    # Function to extract Spotify playlist tracks
    async def extract_spotify_playlist(playlist_link):
        try:
            # Extract playlist ID from the link
            if "spotify.com/playlist/" in playlist_link:
                playlist_id = playlist_link.split("playlist/")[1].split("?")[0]
            else:
                return None, "Invalid Spotify playlist link"
                
            # Get playlist tracks
            results = []
            tracks = []
            offset = 0
            limit = 100  # Spotify API limit

            # Get initial batch of tracks
            response = sp.playlist_items(
                playlist_id,
                offset=offset,
                limit=limit,
                fields='items.track.name,items.track.artists.name,total'
            )
            
            total_tracks = response['total']
            
            # Extract track info from response
            for item in response['items']:
                if item['track']:
                    track = item['track']
                    artist_name = track['artists'][0]['name'] if track['artists'] else "Unknown Artist"
                    track_name = track['name']
                    tracks.append(f"{artist_name} - {track_name}")
            
            # Get remaining tracks if necessary
            while len(tracks) < total_tracks:
                offset += limit
                response = sp.playlist_items(
                    playlist_id,
                    offset=offset,
                    limit=limit,
                    fields='items.track.name,items.track.artists.name'
                )
                
                for item in response['items']:
                    if item['track']:
                        track = item['track']
                        artist_name = track['artists'][0]['name'] if track['artists'] else "Unknown Artist"
                        track_name = track['name']
                        tracks.append(f"{artist_name} - {track_name}")
            
            return tracks, f"Found {len(tracks)} tracks in playlist"
        except SpotifyException as e:
            return None, f"Spotify API error: {str(e)}"
        except Exception as e:
            return None, f"Error processing Spotify playlist: {str(e)}"

    @client.command(name="playlist")
    async def playlist(ctx, *, playlist_link):
        """Play songs from a Spotify playlist"""
        try:
            # Check if user is in voice channel
            if ctx.author.voice is None:
                await ctx.send("WWWAAAAAAAHHHHHHHH! (No life signs detected!)")
                return
            
            # Connect to voice channel if not already connected
            if ctx.voice_client is None:
                voice_client = await ctx.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
            else:
                voice_client = ctx.voice_client
                voice_clients[voice_client.guild.id] = voice_client
            
            # Process message
            await ctx.send("Processing Spotify playlist... This may take a moment.")
            
            # Extract tracks from Spotify playlist
            tracks, message = await extract_spotify_playlist(playlist_link)
            
            if not tracks:
                await ctx.send(message)
                return
                
            await ctx.send(message)
            
            # Process first 50 tracks (to avoid overloading)
            max_tracks = min(50, len(tracks))
            await ctx.send(f"Adding first {max_tracks} tracks to queue...")
            
            # Add first track to play immediately if nothing is playing
            first_track = tracks[0]
            first_yt_link = await get_youtube_link(first_track)
            
            if first_yt_link:
                # Handle first track
                if ctx.voice_client.is_playing():
                    queues.setdefault(ctx.guild.id, []).append(first_yt_link)
                    await ctx.send(f"Added to queue: {first_track}")
                else:
                    await play(ctx, link=first_yt_link)
            
            # Add the rest to queue
            tracks_added = 1
            for track in tracks[1:max_tracks]:
                yt_link = await get_youtube_link(track)
                if yt_link:
                    queues.setdefault(ctx.guild.id, []).append(yt_link)
                    tracks_added += 1
                
                # Add a small delay to avoid rate limiting
                await asyncio.sleep(0.5)
            
            await ctx.send(f"Successfully added {tracks_added} tracks from the playlist to queue!")
            
        except Exception as e:
            print(f"Error in playlist command: {e}")
            await ctx.send(f"Error processing playlist: {str(e)}")
    
    
    
    
    @client.command(name="play")
    async def play(ctx, *, link):
        """Play a song from YouTube or Spotify"""
        
        # Check if user is in voice channel first
        if ctx.author.voice is None:
            await ctx.send("WWWAAAAAAAHHHHHHHH! (No life signs detected!)")
            return
        
        # Connect to voice channel
        try:
            if ctx.voice_client is None:
                voice_client = await ctx.author.voice.channel.connect()
                voice_clients[voice_client.guild.id] = voice_client
                await asyncio.sleep(1)  # Give the connection time to stabilize
            else:
                voice_client = ctx.voice_client
                voice_clients[voice_client.guild.id] = voice_client
        except Exception as e:
            print(f"Error connecting to voice channel: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"Error connecting to voice channel: {str(e)}")
            return

        try:
            # Check if it's a Spotify playlist and redirect to playlist command
            if "spotify.com/playlist/" in link:
                await ctx.send("Spotify playlist detected! Redirecting to playlist command...")
                await playlist(ctx, playlist_link=link)
                return
            
            # Check if it's a Spotify track and convert it to search query
            if "spotify.com/track/" in link:
                try:
                    # Extract track ID
                    track_id = link.split("track/")[1].split("?")[0]
                    track_info = sp.track(track_id)
                    
                    # Get artist and track name
                    artist = track_info["artists"][0]["name"]
                    track_name = track_info["name"]
                    
                    # Create search query
                    link = f"{artist} - {track_name}"
                    await ctx.send(f"Spotify track detected! Searching for: {link}")
                except Exception as e:
                    print(f"Error processing Spotify track: {e}")
                    # If error, continue with original link
            
            # If not a YouTube link, search for it
            if youtube_base_url not in link:
                query_string = urllib.parse.urlencode({
                    'search_query': link
                })

                content = urllib.request.urlopen(
                    youtube_results_url + query_string
                )

                search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
                
                if not search_results:
                    await ctx.send("Could not find any results for that search!")
                    return

                link = youtube_watch_url + search_results[0]

            print(f"Current FFmpeg path: {ffmpeg_path}")
            print(f"Processing link: {link}")

            # Extract video info and play
            loop = asyncio.get_event_loop()
            
            try:
                await ctx.send("🔍 Searching for song...")
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
                song_url = data['url']
                title = data.get('title', 'Unknown Title')
                
                print(f"Extracted title: {title}")
                print(f"Stream URL obtained: {song_url[:80]}...")
                
                # Create player with explicit FFmpeg path
                http_headers = data.get('http_headers', {})
                player = await create_player(song_url, http_headers)
                
                if player is None:
                    await ctx.send("Error creating audio player. Please check if FFmpeg is installed correctly.")
                    return
                
                # Check if already playing
                if voice_clients[ctx.guild.id].is_playing():
                    queues.setdefault(ctx.guild.id, []).append(link)
                    await ctx.send(f"➕ Added to queue: {title}")
                else:
                    # Make sure voice client is connected
                    if not voice_clients[ctx.guild.id].is_connected():
                        await ctx.send("Voice client disconnected unexpectedly. Please try again.")
                        return
                        
                    voice_clients[ctx.guild.id].play(
                        player, 
                        after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
                    )
                    await ctx.send(f"🎵 Bleep Bloop (Now Playing!) {title}")
                    
            except Exception as e:
                print(f"Error extracting info or playing audio: {e}")
                import traceback
                traceback.print_exc()
                await ctx.send(f"Error playing audio: {str(e)}")
                
        except Exception as e:
            print(f"Error in play command: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"Error: {str(e)}")
            
            
            
    @client.command(name="skip")
    async def skip(ctx):
        
        if ctx.author.voice is None:
            await ctx.send("WWWAAAAAAAHHHHHHHH! (No life signs detected!)")
            return
        
        if ctx.voice_client and ctx.voice_client.is_playing():
            await ctx.send("NEXT!")
            ctx.voice_client.stop()  # Stop the current song
            await play_next(ctx)  # Play next song
        else:
            await ctx.send("Wha- Impossible! (No song is currently playing)")


    
    @client.command(name="previous")
    async def previous(ctx):
        if ctx.guild.id in history and len(history[ctx.guild.id]) > 0:
            # Get the last played song
            last_song = history[ctx.guild.id].pop()  
            
            # Add current song to history if it's playing
            if ctx.voice_client and ctx.voice_client.is_playing():
                # We need to know what's currently playing
                # For now, just stop the current song
                ctx.voice_client.stop()
                
            # Add the previous song to the front of the queue
            queues.setdefault(ctx.guild.id, []).insert(0, last_song)
            await ctx.send("Going back in time!")
            await play_next(ctx)  # Play previous song
        else:
            await ctx.send("Time machine broke! (No previous songs found)")      
             
            

            
    @client.command(name="cl")
    async def clear_queue(ctx):
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
            await ctx.send("Pop! (Queue cleared)")
        else:
            await ctx.send("Oh! (No queue to clear)")

    @client.command(name="pause")
    async def pause(ctx):
        try:
            if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
                voice_clients[ctx.guild.id].pause()
                await ctx.send("Paused!")
            else:
                await ctx.send("Nothing is playing to pause!")
        except Exception as e:
            print(f"Error in pause command: {e}")
            await ctx.send(f"Error: {str(e)}")

    @client.command(name="resume")
    async def resume(ctx):
        try:
            if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_paused():
                voice_clients[ctx.guild.id].resume()
                await ctx.send("Resumed!")
            else:
                await ctx.send("Nothing is paused to resume!")
        except Exception as e:
            print(f"Error in resume command: {e}")
            await ctx.send(f"Error: {str(e)}")

    @client.command(name="stop")
    async def stop(ctx):
        try:
            if ctx.guild.id in voice_clients:
                voice_clients[ctx.guild.id].stop()
                await voice_clients[ctx.guild.id].disconnect()
                del voice_clients[ctx.guild.id]
                await ctx.send("Eeeee... va?")
            else:
                await ctx.send("I'm not connected to any voice channel!")
        except Exception as e:
            print(f"Error in stop command: {e}")
            await ctx.send(f"Error: {str(e)}")

    @client.command(name="queue")
    async def queue(ctx, *, url):
        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []
        queues[ctx.guild.id].append(url)
        await ctx.send("Meep meep (Added to queue!)")
        
    @client.command(name="show")
    async def show_queue(ctx):
        if ctx.guild.id in queues and queues[ctx.guild.id]:
            song_titles = []
            for url in queues[ctx.guild.id]:
                try:
                    loop = asyncio.get_event_loop()
                    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                    song_titles.append(data.get('title', 'Unknown title'))  # Show default title if no title found
                except Exception as e:
                    song_titles.append(f"Unknown title (Error: {str(e)})")
                
            # Format list of songs
            queue_list = "\n".join(f"{index + 1}. {title}" for index, title in enumerate(song_titles))
            await ctx.send(f"Current Queue:\n{queue_list}")
        else:
            await ctx.send("[Starts mogging you]")
        
        
        
    @client.command(name="join")
    async def join(ctx):
        """Join voice channel with diagnostics"""
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                try:
                    await ctx.send(f"Attempting to join **{channel.name}**...")
                    voice_client = await channel.connect(timeout=10.0, reconnect=True)
                    voice_clients[ctx.guild.id] = voice_client
                    
                    # Wait a moment for connection to stabilize
                    await asyncio.sleep(1)
                    
                    # Check if still connected
                    if voice_client.is_connected():
                        await ctx.send(f"✅ WALL-E successfully joined **{channel.name}**!")
                        print(f"Successfully connected to {channel.name} (ID: {channel.id})")
                    else:
                        await ctx.send("⚠️ Connected but voice client shows disconnected. Please try again.")
                        print("Voice client connected but reports not connected")
                        
                except asyncio.TimeoutError:
                    await ctx.send("❌ Connection timed out. Please try again.")
                    print("Voice connection timed out")
                except Exception as e:
                    await ctx.send(f"❌ Error connecting: {str(e)}")
                    print(f"Voice connection error: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                await ctx.send("BEEEEEP! (Already connected!)")
        else:
            await ctx.send("WWAAAAAAAAAAHHHHH! (You're not in a voice channel!)")
            
            
            
            
    @client.command(name="leave")
    async def leave(ctx):
        if ctx.author.voice:  # Makes sure someone is in voice channel
            if ctx.voice_client:  # Check if bot is in a voice channel
                if ctx.voice_client.is_playing():  # Stop any ongoing playback
                    ctx.voice_client.stop()

                await ctx.voice_client.disconnect()  # Leave the voice channel
                await ctx.send("Eeee...va?")
            else:
                await ctx.send("BEEEEEP!")
        else:
            await ctx.send("WWWAAAAAAAAHHHHHH!")







    @client.command(name="ltg")
    async def lowtiergod(ctx):
        try:
            # YouTube link
            youtube_link = "https://www.youtube.com/watch?v=UZROG81-V80"

            # User has to be in voice channel
            if ctx.author.voice is None:
                await ctx.send("Join a voice channel to use this command for a surprise :)")
                return
            
            # Connect bot to voice channel
            if ctx.voice_client is None:
                voice_client = await ctx.author.voice.channel.connect()
                voice_clients[ctx.guild.id] = voice_client
            else:
                voice_client = ctx.voice_client

         
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(youtube_link, download=False))

            song_url = data['url']
            title = data.get('title', 'Unknown Title')
            
            # Create player with explicit FFmpeg path
            player = await create_player(song_url)
            
            if player is None:
                await ctx.send("Error creating audio player. Please check if FFmpeg is installed correctly.")
                return

            # if audio is already playing
            if voice_client.is_playing():
                await ctx.send("Audio being played already.")
            else:
                # play audio
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
                await ctx.send(f"Enjoy XD")

        except Exception as e:
            await ctx.send(f"An error occurred while trying to play the audio: {str(e)}")
            print(f"Error in play_audio: {e}")

    @client.command(name="miku")
    async def hatsune_miku(ctx):
        try:
            youtube_link = "https://www.youtube.com/watch?v=_-2dIuV34cs"

          
            if ctx.author.voice is None:
                await ctx.send("Miku requests you to join a voice channel")
                return
            
           
            if ctx.voice_client is None:
                voice_client = await ctx.author.voice.channel.connect()
                voice_clients[ctx.guild.id] = voice_client
            else:
                voice_client = ctx.voice_client

         
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(youtube_link, download=False))

            song_url = data['url']
            title = data.get('title', 'Unknown Title')
            
            # Create player with explicit FFmpeg path
            player = await create_player(song_url)
            
            if player is None:
                await ctx.send("Error creating audio player. Please check if FFmpeg is installed correctly.")
                return

            if voice_client.is_playing():
                await ctx.send("Audio being played already.")
            else:
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
                await ctx.send(f"MIKU MIKU MIKU MIKU MIKU MIKU")

        except Exception as e:
            await ctx.send(f"An error occurred while trying to play the audio: {str(e)}")
            print(f"Error in play_audio: {e}")
            
            
            

    @client.command(name="ffmpeg")
    async def check_ffmpeg(ctx):
        """Check if FFmpeg is installed and available"""
        try:
            import shutil
            
            # Check if FFmpeg is in PATH
            found_in_path = shutil.which('ffmpeg')
            
            # Check common installation locations
            common_paths = [
                'C:\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
            ]
            
            found_ffmpeg = found_in_path
            if not found_ffmpeg:
                for path in common_paths:
                    if os.path.exists(path):
                        found_ffmpeg = path
                        break
            
            if found_ffmpeg:
                await ctx.send(f"✅ FFmpeg found at: `{found_ffmpeg}`")
                
                # Check what the bot is actually using
                if ffmpeg_path:
                    await ctx.send(f"🤖 Bot is configured to use: `{ffmpeg_path}`")
                    await ctx.send("✅ Bot can play audio!")
                else:
                    await ctx.send("⚠️ Bot is NOT configured to use FFmpeg")
                
                # Check version
                try:
                    result = subprocess.run(
                        [found_ffmpeg, "-version"], 
                        capture_output=True, 
                        text=True, 
                        timeout=5
                    )
                    version_info = result.stdout.split('\n')[0] if result.stdout else "Unknown version"
                    await ctx.send(f"📋 {version_info}")
                    
                    # Check if it's in PATH (optional info)
                    if found_in_path:
                        await ctx.send("ℹ️ FFmpeg is in your PATH (optional but recommended)")
                    else:
                        await ctx.send("ℹ️ FFmpeg not in PATH, but bot found it anyway - you're good!")
                        
                except Exception as e:
                    await ctx.send(f"⚠️ Found FFmpeg but couldn't get version: {str(e)}")
            else:
                await ctx.send("❌ FFmpeg not found!")
                await ctx.send("📥 Install FFmpeg from: https://ffmpeg.org/download.html")
                await ctx.send("📌 For Windows: Download, extract to `C:\\ffmpeg`, and add `C:\\ffmpeg\\bin` to PATH")
                
        except Exception as e:
            await ctx.send(f"❌ Error checking FFmpeg: {str(e)}")
            import traceback
            traceback.print_exc()



    @client.command(name="help")
    async def help(ctx):

        embed = discord.Embed(title="Help Menu", description="List of available commands:", color=discord.Color.blue())
        
        embed.add_field(name="!play <song/link>", value="Play a song or add it to the queue", inline=False)
        embed.add_field(name="!playlist <spotify_playlist_link>", value="Play songs from a Spotify playlist", inline=False)
        embed.add_field(name="!queue <song/link>", value="Add a song to the queue", inline=False)
        embed.add_field(name="!show", value="Display the current queue", inline=False)
        embed.add_field(name="!cl", value="Clear the song queue", inline=False)
        embed.add_field(name="!pause", value="Pause the current song", inline=False)
        embed.add_field(name="!resume", value="Resume the paused song", inline=False)
        embed.add_field(name="!stop", value="Stop playing and disconnect", inline=False)
        embed.add_field(name="!join", value="Join the voice channel only", inline=False)
        embed.add_field(name="!leave", value="leave the voice channel", inline=False)
        embed.add_field(name="!skip", value="Skip the song that is currently playing", inline=False)
        embed.add_field(name="!previous", value="Go back to the previous song", inline=False)
        embed.add_field(name="!ffmpeg", value="Check if FFmpeg is installed and working", inline=False)


        await ctx.send(embed=embed)
    
    client.run(TOKEN)
