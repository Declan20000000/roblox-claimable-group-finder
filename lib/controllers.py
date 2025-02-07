from .workers import worker_func
from .utils import slice_list, slice_range, update_stats
from multiprocessing import Process, Queue
from threading import Thread
from time import time

class Controller:
    def __init__(self, arguments):
        self.arguments = arguments
        self.count_queue = Queue()
        self.workers = []
        self.proxies = []
        
        if self.arguments.proxy_file:
            self.load_proxies()
        self.start_workers()
        self.start_stat_thread()

    def load_proxies(self):
        proxies = set()
        with self.arguments.proxy_file as fp:
            while (line := fp.readline()):
                try:
                    line = line.rstrip()
                    host, _, port = line.partition(":")
                    addr = (host.lower(), int(port))
                    if not addr in proxies:
                        proxies.add(addr)
                except Exception as err:
                    print(f"Error while loading proxy '{line}': {err!r}")
        self.proxies.extend(proxies)
            
    def start_workers(self):
        for num in range(self.arguments.workers):
            worker = Process(
                target=worker_func,
                name=f"Worker-{num}",
                daemon=True,
                kwargs=dict(
                    thread_count=self.arguments.threads,
                    count_queue=self.count_queue,
                    proxy_list=slice_list(self.proxies, num, self.arguments.workers),
                    gid_ranges=[
                        slice_range(gid_range, num, self.arguments.workers)
                        for gid_range in self.arguments.range
                    ],
                    gid_cutoff=self.arguments.cut_off,
                    gid_chunk_size=self.arguments.chunk_size,
                    webhook_url=self.arguments.webhook_url,
                    timeout=self.arguments.timeout
                )
            )
            self.workers.append(worker)
        for worker in self.workers:
            worker.start()

    def join_workers(self):
        for worker in self.workers:
            worker.join()

    def start_stat_thread(self):
        def stat_updater_func():
            count_cache = []
            while any(w.is_alive() for w in self.workers):
                count_cache.append(self.count_queue.get())
                t = time()
                count_cache = [x for x in count_cache if 60 > t - x[0]]
                cpm = sum([x[1] for x in count_cache])
                update_stats(f"CPM: {cpm}")
            
        thread = Thread(
            target=stat_updater_func,
            name="Stat-Thread",
            daemon=True)
        thread.start()