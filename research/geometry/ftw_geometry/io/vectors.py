"""Bounded remote GeoParquet access; preserves original geometry bytes."""

import io
import urllib.request


class RangeReader(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.pos, self.transferred = url, size, 0, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (
            offset
            if whence == 0
            else self.pos + offset
            if whence == 1
            else self.size + offset
        )
        return self.pos

    def read(self, size=-1):
        size = min(self.size - self.pos, size if size >= 0 else self.size - self.pos)
        if size <= 0:
            return b""
        start, end = self.pos, self.pos + size - 1
        request = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "Mozilla/5.0 FTW-pilot",
                "Range": f"bytes={start}-{end}",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            if (
                response.status != 206
                or len(data) != size
                or not response.headers.get("Content-Range", "").startswith(
                    f"bytes {start}-{end}/"
                )
            ):
                raise ValueError("Server did not honor exact byte range")
        self.pos += size
        self.transferred += size
        return data


def overlapping_groups(metadata, bounds):
    result = []
    for i in range(metadata.num_row_groups):
        group = metadata.row_group(i)
        stats = {
            group.column(k).path_in_schema: group.column(k).statistics
            for k in range(group.num_columns)
        }
        if any(
            stats.get(f"bbox.{k}") is None or not stats[f"bbox.{k}"].has_min_max
            for k in ("xmin", "ymin", "xmax", "ymax")
        ):
            raise ValueError(
                "Missing bbox statistics; refusing uncontrolled whole-file scan"
            )
        if (
            stats["bbox.xmin"].min <= bounds[2]
            and stats["bbox.xmax"].max >= bounds[0]
            and stats["bbox.ymin"].min <= bounds[3]
            and stats["bbox.ymax"].max >= bounds[1]
        ):
            result.append(i)
    return result
