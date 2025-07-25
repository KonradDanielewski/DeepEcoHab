import os
import re
import shutil
import sys
import subprocess
import PySpin
import numpy as np
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class CameraWorker(QObject):
    frame_ready   = pyqtSignal(np.ndarray)   # preview
    finished      = pyqtSignal()
    error         = pyqtSignal(str)

    def __init__(self, video_dir, videoname):
        super().__init__()
        self.video_dir   = None
        self.videoname   = videoname
        self.proc        = None
        self.recording   = False
        self.csv_log     = None
        self._stop       = False
        self._fps        = 30

    @pyqtSlot()
    def start(self):
        """Entry point run by QThread."""
        try:
            # >>> ALL PySpin work happens here, in the worker thread <<<
            system = PySpin.System.GetInstance()
            cam_list = system.GetCameras()
            if cam_list.GetSize() == 0:
                raise RuntimeError("No FLIR camera found")

            cam = cam_list.GetByIndex(0)
            cam.Init()
            nodemap = cam.GetNodeMap()

            enum  = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
            enum.SetIntValue(enum.GetEntryByName("Continuous").GetValue())

            cam.BeginAcquisition()

            while not self._stop:
                img = cam.GetNextImage(1000)
                if img.IsIncomplete():
                    img.Release()
                    continue
                try:
                    frame = img.GetNDArray()
    
                    # GUI preview
                    self.frame_ready.emit(frame)
    
                    # optional write
                    if self.recording and self.proc:
                        try:
                            self.proc.stdin.write(frame.tobytes())
                            if self.csv_log:
                                timestamp_ns = img.GetTimeStamp()
                                self.csv_log.write(f"{timestamp_ns}\n")
             
                        except (BrokenPipeError, OSError) as e:
                            self.error.emit(f"FFmpeg write error: {e}")
                            self.stop_recording()
                finally:
                    img.Release()

            # clean-up
            self.stop_recording()
            cam.EndAcquisition()
            cam.DeInit()
            system.ReleaseInstance()
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit()
                    
            

    def start_recording(self, width, height):
        if self.recording:
            return
    
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        videoname = f"{self.videoname}_{timestamp}_%03d.mp4"
        
        outfile = os.path.join(self.video_dir, videoname)
            
        self.proc = start_ffmpeg_pipe(width, height, self._fps, outfile)
        logname = f"{self.videoname}_{timestamp}.csv"
        logpath = os.path.join(self.video_dir, logname)
        self.csv_log = open(logpath, mode="w", buffering=1)
        
        
        self._frame_idx = 0
        self._segment_idx = 0
        self.segment_length_frames = int(3600 * self._fps)
        
        self.csv_log.write("segment_index,frame_index,timestamp_ns\n")
        
        
        
        self.recording = True

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=2)
            except Exception:
                pass
            self.proc = None

    def stop(self):
        self._stop = True
        
        
            
            
def pick_encoder(prefer_hevc=True):
    """Return (codec_name, extra_args[]) chosen for this machine.

    prefer_hevc=True → try HEVC/H.265 first, else H.264.
    """

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg not found in PATH")

    output = subprocess.check_output(
        ["ffmpeg", "-v", "quiet", "-hide_banner", "-encoders"],
        text=True, stderr=subprocess.DEVNULL
    )

    # 3. Parse encoder names from lines like: " V..... h264_nvenc ..."
    enc = set()
    for line in output.splitlines():
        match = re.match(r"\s*[A-Z\.]{6}\s+(\S+)", line)
        if match:
            enc.add(match.group(1))
    # helpers
    def have(x): return x in enc

    # NVENC first (fastest)
    if prefer_hevc and have("hevc_nvenc"):
        return "hevc_nvenc", ["-preset", "p4", "-rc-lookahead", "10"]
    if have("h264_nvenc"):
        return "h264_nvenc", ["-preset", "p4", "-rc-lookahead", "10"]

    # Intel / VAAPI
    if prefer_hevc and have("hevc_vaapi"):
        return "hevc_vaapi", ["-vf", "format=nv12,hwupload", "-qp", "23"]
    if have("h264_vaapi"):
        return "h264_vaapi", ["-vf", "format=nv12,hwupload", "-qp", "23"]

    # Apple VideoToolbox (macOS)
    if sys.platform == "darwin":
        if prefer_hevc and have("hevc_videotoolbox"):
            return "hevc_videotoolbox", ["-b:v", "6M"]
        if have("h264_videotoolbox"):
            return "h264_videotoolbox", ["-b:v", "6M"]

    # Software fall-backs
    if prefer_hevc and have("libx265"):
        return "libx265", ["-preset", "medium", "-crf", "28"]
    if have("libx264"):
        return "libx264", ["-preset", "fast", "-crf", "23"]

    raise RuntimeError("No suitable encoder found (checked hw & sw)")

def start_ffmpeg_pipe(width, height, fps, output_file):
    codec, extra = pick_encoder(prefer_hevc=False)  # or False for H.264 first
    
    codec = "libx264"
    extra = ["-preset", "fast", "-crf", "23"]

    pix_fmt = "gray" if codec.endswith("_nvenc") else "yuv420p"

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", pix_fmt,
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",              # stdin
        "-c:v", codec,          # encoder chosen
        *extra,                 # codec-specific opts
        "-g", "5",
        "-force_key_frames", "expr:gte(t,n_forced*6)",
        "-segment_time", "3600",
        "-reset_timestamps", "1",
        "-f", "segment",
        "-an",
        output_file
    ]

    return subprocess.Popen(cmd, stdin=subprocess.PIPE)        