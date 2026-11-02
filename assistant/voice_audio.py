"""PCM format conversion with continuous sample positions, without disk audio."""
import numpy as np


class PCMConverter:
    def __init__(self, rate: int, channels: int, kind: str):
        self.rate, self.channels, self.kind = rate, channels, kind
        self.dtype = {"Int16": "<i2", "Int32": "<i4", "Float": "<f4", "UInt8": "u1"}[kind]
        self.frame_bytes = np.dtype(self.dtype).itemsize * channels
        self.pending = b""
        self.tail = np.empty(0, dtype=np.float32)
        self.count = 0
        self.next_position = 0.0

    def convert(self, data: bytes):
        data = self.pending + data
        count = len(data) // self.frame_bytes * self.frame_bytes
        self.pending = data[count:]
        if not count:
            return np.empty(0, dtype=np.float32)
        values = np.frombuffer(data[:count], dtype=self.dtype).astype(np.float32)
        if self.kind == "UInt8":
            values = (values-128)/128
        elif self.kind in {"Int16", "Int32"}:
            values /= 32768 if self.kind == "Int16" else 2147483648
        values = values.reshape(-1, self.channels).mean(axis=1)
        if self.rate == 16000:
            return values
        base = self.count - len(self.tail)
        self.count += len(values)
        samples = np.concatenate((self.tail, values))
        positions = np.arange(self.next_position, self.count-1, self.rate/16000)
        result = np.interp(positions-base, np.arange(len(samples)), samples).astype(np.float32)
        if len(positions):
            self.next_position = positions[-1] + self.rate/16000
        self.tail = samples[-1:]
        return result
