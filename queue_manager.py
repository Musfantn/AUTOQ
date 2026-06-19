class QueueManager:

    def __init__(self):
        self.current = 0

    def next(self):
        self.current += 1
        return f"{self.current:03d}"

    def reset(self):
        self.current = 0

    def set_number(self,n):
        self.current = n

    def get(self):
        return f"{self.current:03d}"