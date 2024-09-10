from time import sleep

from vlc import Instance, Media, MediaPlayer, State

if __name__ == "__main__":
    instance: Instance = Instance("--pitch-shift 4")
    player: MediaPlayer = instance.media_player_new()
    media: Media = instance.media_new_path("/Users/gosha/Downloads/Pentatonix - Carol of the Bells.mp3")
    player.set_media(media)
    print("Playing")
    player.play()
    while player.get_state() not in (State.Ended, State.Stopped, State.Paused):
        sleep(0.25)
    print("Done")

