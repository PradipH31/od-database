import os
import json
from urllib.parse import urlparse
from timeout_decorator.timeout_decorator import TimeoutError
from threading import Thread
from queue import Queue, Empty


class TooManyConnectionsError(Exception):
    pass


class File:

    def __init__(self, name: str, size: int, mtime: str, path: str, is_dir: bool):
        self.name = name
        self.size = size
        self.mtime = mtime
        self.path = path
        self.is_dir = is_dir

    def __str__(self):
        return ("DIR " if self.is_dir else "FILE ") + self.path + "/" + self.name

    def to_json(self):
        return json.dumps({
            "name": self.name,
            "size": self.size,
            "mtime": self.mtime,
            "path": self.path,
        })


class RemoteDirectory:

    SCHEMES = ()

    def __init__(self, base_url):
        self.base_url = base_url

    def list_dir(self, path: str) -> list:
        raise NotImplementedError

    def close(self):
        pass


class RemoteDirectoryFactory:

    from crawler.ftp import FtpDirectory
    from crawler.http import HttpDirectory
    DIR_ENGINES = (FtpDirectory, HttpDirectory)

    @staticmethod
    def get_directory(url) -> RemoteDirectory:

        parsed_url = urlparse(url)

        for dir_engine in RemoteDirectoryFactory.DIR_ENGINES:
            if parsed_url.scheme in dir_engine.SCHEMES:
                return dir_engine(url)


class RemoteDirectoryCrawler:

    def __init__(self, url, max_threads: int):
        self.url = url
        self.max_threads = max_threads

    def crawl_directory(self):

        try:
            directory = RemoteDirectoryFactory.get_directory(self.url)
            root_listing = directory.list_dir("/dl2/")  # todo get path
            directory.close()
        except TimeoutError:
            return

        in_q = Queue(maxsize=0)
        files_q = Queue(maxsize=0)
        for f in root_listing:
            if f.is_dir:
                in_q.put(f)
            else:
                files_q.put(f)

        threads = []
        for i in range(self.max_threads):
            worker = Thread(target=RemoteDirectoryCrawler._process_listings, args=(self.url, in_q, files_q))
            threads.append(worker)
            worker.start()

        in_q.join()
        print("DONE")

        # Kill threads
        for _ in threads:
            in_q.put(None)
        for t in threads:
            t.join()

        print(files_q.qsize())
        return []

    @staticmethod
    def _process_listings(url: str, in_q: Queue, files_q: Queue):

        directory = RemoteDirectoryFactory.get_directory(url)

        while directory:

            try:
                file = in_q.get(timeout=60)
            except Empty:
                break

            if file is None:
                break

            try:
                listing = directory.list_dir(os.path.join(file.path, file.name, ""))

                for f in listing:
                    if f.is_dir:
                        in_q.put(f)
                    else:
                        files_q.put(f)
            except TooManyConnectionsError as e:
                print("TOO MANY CONNNS")
            except TimeoutError:
                pass
            finally:
                in_q.task_done()