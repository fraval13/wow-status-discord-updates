#!/bin/sh
# Encode the offline-rendered, 20 fps, 12-second scene. No audio track.
set -eu
frames_dir="${1:-dist/motion-frames}"
ffmpeg -y -framerate 20 -i "$frames_dir/%04d.png" -an \
    -vf 'scale=out_color_matrix=bt709,format=yuv420p' \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
    -c:v libvpx-vp9 -b:v 0 -crf 36 -row-mt 1 -cpu-used 4 \
    website/assets/adventure-motion.webm -loglevel error
ffmpeg -y -framerate 20 -i "$frames_dir/%04d.png" -an \
    -vf 'scale=out_color_matrix=bt709,format=yuv420p' \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
    -c:v libx264 -crf 26 -preset medium -movflags +faststart \
    website/assets/adventure-motion.mp4 -loglevel error
