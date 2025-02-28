import os
import shutil
from pathlib import Path
from typing import TextIO


class ResourceHandler:
    class Resource:
        def __init__(self, path: Path):
            self.path: Path = path
            self.claimed: bool = True
            self.io_wrapper: TextIO | None = None
            self.is_open = True
            self.path.mkdir()

        def open(self, *args, **kwargs) -> TextIO:
            if self.claimed:
                if self.io_wrapper is None or self.io_wrapper.closed:
                    self.io_wrapper = open(self.path, *args, **kwargs)
                    return self.io_wrapper
                else:
                    raise RuntimeError(f"{self.path} already open")
            else:
                raise RuntimeError(f"Resource at {self.path} has been freed")

        def close(self):
            self.is_open = False
            if self.claimed:
                if self.io_wrapper is None or self.io_wrapper.closed:
                    self.claimed = False
                    if os.path.exists(self.path):
                        shutil.rmtree(self.path)
                    else:
                        print(f"Warning: directory {self.path} does not exist")
                else:
                    raise RuntimeError(f"{self.path} is still open")
            else:
                raise RuntimeError(f"Resource at {self.path} has already been freed")

    def __init__(self, directory: str):
        self.directory = directory
        self.next_id = 0
        self.claims = []
        self.free_all()

    def free_all(self):
        for claim in self.claims:
            if claim.claimed:
                claim.close()
        shutil.rmtree(self.directory)
        os.mkdir(self.directory)

    def claim(self):
        resource_path = os.path.join(self.directory, str(self.next_id))
        self.next_id += 1
        claim = ResourceHandler.Resource(Path(resource_path))
        self.claims.append(claim)
        return claim
