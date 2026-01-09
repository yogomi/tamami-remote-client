"""
Webブラウザでリアルタイム波形を表示する。

依存:  flask, plotly, numpy

起動後 http://localhost:5000 にアクセスすると波形が表示される。
"""
from typing import Optional
import threading
import queue
import numpy as np
from flask import Flask, render_template, Response
import plotly.graph_objs as go
import json
import time


class WaveformVisualizerWeb:
    """Webブラウザ向けリアルタイム波形可視化クラス. 

    Args:
        sample_rate: サンプリングレート(Hz).
        channels: チャネル数(1=mono, 2=stereo).
        window_seconds: 表示ウィンドウ長(秒).
        decimate: 描画用に毎 decimate 番目のサンプルだけを使う(負荷低減).
        port: Webサーバーのポート番号.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 1,
        window_seconds: int = 5,
        decimate: int = 1,
        port: int = 5000,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.window_seconds = window_seconds
        self.decimate = max(1, int(decimate))
        self.port = port
        self._buf_len = int(self.sample_rate * self.window_seconds)
        self._buffer = np.zeros(self._buf_len, dtype=np.float32)
        self._q:  "queue.Queue[np.ndarray]" = queue.Queue()
        self._running = False
        self._lock = threading.Lock()
        self._app = Flask(__name__)
        self._setup_routes()

    def add_frames(self, frames, dtype:  str = "int16") -> None:
        """音声フレームをキューへ追加する.

        Args:
            frames: bytes または numpy.ndarray
            dtype: bytes を渡す場合のサンプル dtype (e.g.  'int16').
        """
        if isinstance(frames, (bytes, bytearray)):
            arr = np.frombuffer(frames, dtype=dtype)
        else:
            arr = np.asarray(frames)
        if arr.ndim == 1 and self.channels == 2:
            arr = arr.reshape(-1, 2)[:, 0]
        elif arr.ndim == 2: 
            arr = arr[: , 0]
        if np.issubdtype(arr. dtype, np.integer):
            maxval = np.iinfo(arr.dtype).max
            arr = arr. astype(np.float32) / float(maxval)
        else:
            arr = arr.astype(np.float32)
        if self. decimate > 1:
            arr = arr[::  self.decimate]
        try:
            self._q.put_nowait(arr)
        except queue.Full:
            pass

    def _drain_queue_to_buffer(self) -> None:
        with self._lock:
            while not self._q.empty():
                arr = self._q.get_nowait()
                n = arr.shape[0]
                if n >= self._buf_len:
                    self._buffer[: ] = arr[-self._buf_len :]
                else:
                    self._buffer[:-n] = self._buffer[n:]
                    self._buffer[-n:] = arr

    def _setup_routes(self) -> None:
        @self._app.route("/")
        def index():
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Waveform Visualizer</title>
                <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
            </head>
            <body>
                <h1>Realtime Waveform</h1>
                <div id="chart" style="width: 100%;height:400px;"></div>
                <script>
                    const layout = {
                        xaxis: {title: 'Time (seconds)'},
                        yaxis:  {title: 'Amplitude', range: [-1, 1]},
                        margin: {l: 50, r: 50, t: 50, b: 50}
                    };
                    Plotly.newPlot('chart', [], layout);
                    
                    const eventSource = new EventSource('/stream');
                    eventSource.onmessage = function(e) {
                        const data = JSON.parse(e.data);
                        Plotly.react('chart', [{
                            x: data.x,
                            y: data. y,
                            type: 'scatter',
                            mode:  'lines',
                            line: {width: 1}
                        }], layout);
                    };
                </script>
            </body>
            </html>
            """
            return html

        @self._app.route("/stream")
        def stream():
            def event_stream():
                while self._running:
                    self._drain_queue_to_buffer()
                    with self._lock:
                        t = np.linspace(
                            -self.window_seconds,
                            0.0,
                            num=self._buf_len,
                            endpoint=False
                        )
                        payload = {
                            "x":  t. tolist(),
                            "y": self._buffer.tolist()
                        }
                    yield f"data: {json.dumps(payload)}\n\n"
                    time.sleep(0.05)
            return Response(event_stream(), mimetype="text/event-stream")

    def start(self, debug: bool = False) -> None:
        """Webサーバーを起動する.

        Args:
            debug:  Flaskのデバッグモード. 

        Note:
            別スレッドで起動するため、メインスレッドはブロックされない。
        """
        if self._running:
            return
        self._running = True
        threading.Thread(
            target=lambda: self._app.run(
                host="0.0.0.0",
                port=self.port,
                debug=debug,
                use_reloader=False
            ),
            daemon=True
        ).start()
        print(f"Waveform visualizer started at http://localhost:{self.port}")

    def stop(self) -> None:
        """Webサーバーを停止する."""
        self._running = False
