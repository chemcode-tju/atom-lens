"""Chunked image/movie export jobs; no total file-size or frame-count ceiling."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import atexit
import base64
import json
import math
import shutil
import subprocess
import tempfile
import uuid

from snapshot import save_file
from local_export import prepare_local_file


def ffmpeg_executable() -> str:
    candidates = [shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg",
                  str(Path.home() / ".local/share/structure-viewer-codecs/bin/ffmpeg"),
                  str(Path.home() / "software/miniconda3/envs/atom-draw/bin/ffmpeg"),
                  str(Path.home() / "software/miniconda3/envs/work/bin/ffmpeg")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError("未找到 FFmpeg。请安装视频编码器后重试（Mac: brew install ffmpeg）")


class MediaExports:
    """Each unpredictable ID owns only files created in its private temp folder."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        atexit.register(self.close)

    def close(self) -> None:
        for identifier in list(self.jobs):
            self.cancel({"id": identifier})

    def begin(self, arguments: dict[str, Any]) -> dict[str, Any]:
        kind, name = arguments.get("kind"), arguments.get("name")
        from snapshot import validate_name
        validate_name(name)
        suffix = Path(name).suffix
        if kind not in {"image", "animation"} or (suffix in {".gif", ".mov", ".mp4"}) != (kind == "animation"):
            raise ValueError("导出类型与格式不符")
        rate = float(arguments.get("fps", 30))
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("帧率必须是正数")
        executable = ffmpeg_executable() if kind == "animation" else None
        identifier = str(uuid.uuid4())
        folder = Path(tempfile.mkdtemp(prefix="structure-export-"))
        self.jobs[identifier] = {"folder": folder, "kind": kind, "name": name, "fps": rate,
                                 "ffmpeg": executable, "frames": 0, "state": "receiving", "chunk": 0}
        return {"id": identifier}

    def get(self, arguments: dict[str, Any]) -> dict[str, Any]:
        identifier = arguments.get("id")
        if identifier not in self.jobs:
            raise ValueError("导出任务不存在，请重新导出")
        return self.jobs[identifier]

    def append(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job = self.get(arguments)
        if job["state"] != "receiving" or arguments.get("chunk") != job["chunk"]:
            raise ValueError("导出分块顺序不正确")
        payload = base64.b64decode(arguments.get("data", ""), validate=True)
        path = job["folder"] / (f"{job['frames']:09d}.png" if job["kind"] == "animation" else job["name"])
        with path.open("ab") as stream:
            stream.write(payload)
        job["chunk"] += 1
        if arguments.get("last"):
            if job["kind"] == "animation":
                with path.open("rb") as stream:
                    header = stream.read(24)
                if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("动画帧不是有效 PNG")
                dimensions = header[16:24]
                if "dimensions" in job and dimensions != job["dimensions"]:
                    raise ValueError("动画各帧尺寸必须一致")
                job["dimensions"] = dimensions
            job["frames"] += 1
            job["chunk"] = 0
            if job["kind"] == "image":
                from snapshot import validate_file
                validate_file(path, job["name"])
                job["state"] = "ready"
        return {"frames": job["frames"]}

    def finish(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job = self.get(arguments)
        if job["state"] != "receiving" or job["kind"] != "animation" or not job["frames"] or job["chunk"]:
            raise ValueError("动画帧尚未传输完整")
        output = job["folder"] / job["name"]
        command = [job["ffmpeg"], "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "2",
                   "-framerate", str(job["fps"]), "-i", str(job["folder"] / "%09d.png")]
        if output.suffix == ".gif":
            command += ["-filter_complex_threads", "1", "-filter_complex",
                        "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a", "-loop", "0"]
        else:
            command += ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2:color=white", "-c:v", "libx264",
                        "-threads", "2", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        log = (job["folder"] / "encoder.log").open("wb")
        try:
            job["process"] = subprocess.Popen(command + [str(output)], stdout=subprocess.DEVNULL, stderr=log)
        finally:
            log.close()
        job["state"] = "encoding"
        return self.status(arguments)

    def status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job = self.get(arguments)
        if job["state"] == "encoding" and job["process"].poll() is not None:
            job["state"] = "ready" if job["process"].returncode == 0 else "error"
            for path in job["folder"].glob("[0-9]*.png"):
                path.unlink()
        result = {"state": job["state"], "frames": job["frames"]}
        if job["state"] == "error":
            result["error"] = (job["folder"] / "encoder.log").read_text(errors="replace")[-3000:]
        return result

    def save(self, params: dict[str, Any]) -> dict[str, Any]:
        arguments = params.get("arguments", {})
        job = self.get(arguments)
        if self.status(arguments)["state"] != "ready":
            raise ValueError("导出尚未完成")
        path = job["folder"] / job["name"]
        if arguments.get("destination") == "helper":
            return prepare_local_file(path, job["name"])
        return save_file(path, job["name"], params)

    def cancel(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job = self.get(arguments)
        process = job.get("process")
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(job["folder"])
        del self.jobs[arguments["id"]]
        return {"cancelled": True}
