import os, shutil


def clean_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def clean_old_files(folder, hours=24):
    import time
    if not os.path.exists(folder):
        return 0
    cutoff = time.time() - (hours * 3600)
    removed = 0
    for root, dirs, files in os.walk(folder, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
                    removed += 1
            except Exception:
                pass
    return removed
