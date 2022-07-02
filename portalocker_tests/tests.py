from __future__ import print_function
from __future__ import with_statement

import multiprocessing
import time

import pytest
import portalocker
from portalocker import utils


def test_exceptions(tmpfile):
    # Open the file 2 times
    a = open(tmpfile, 'a')
    b = open(tmpfile, 'a')

    # Lock exclusive non-blocking
    lock_flags = portalocker.LOCK_EX | portalocker.LOCK_NB

    # First lock file a
    portalocker.lock(a, lock_flags)

    # Now see if we can lock file b
    with pytest.raises(portalocker.LockException):
        portalocker.lock(b, lock_flags)

    # Cleanup
    a.close()
    b.close()


def test_utils_base():
    class Test(utils.LockBase):
        pass


def test_with_timeout(tmpfile):
    # Open the file 2 times
    with pytest.raises(portalocker.AlreadyLocked):
        with portalocker.Lock(tmpfile, timeout=0.1) as fh:
            print('writing some stuff to my cache...', file=fh)
            with portalocker.Lock(
                tmpfile, timeout=0.1, mode='wb',
                fail_when_locked=True
            ):
                pass
            print('writing more stuff to my cache...', file=fh)


def test_without_timeout(tmpfile):
    # Open the file 2 times
    with pytest.raises(portalocker.LockException):
        with portalocker.Lock(tmpfile, timeout=None) as fh:
            print('writing some stuff to my cache...', file=fh)
            with portalocker.Lock(tmpfile, timeout=None, mode='w'):
                pass
            print('writing more stuff to my cache...', file=fh)


def test_without_fail(tmpfile):
    # Open the file 2 times
    with pytest.raises(portalocker.LockException):
        with portalocker.Lock(tmpfile, timeout=0.1) as fh:
            print('writing some stuff to my cache...', file=fh)
            lock = portalocker.Lock(tmpfile, timeout=0.1)
            lock.acquire(check_interval=0.05, fail_when_locked=False)


def test_simple(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    fh = open(tmpfile, 'r+')
    portalocker.lock(fh, portalocker.LOCK_EX)

    fh.seek(13)
    fh.write('foo')

    # Make sure we didn't overwrite the original text
    fh.seek(0)
    assert fh.read(13) == 'spam and eggs'

    portalocker.unlock(fh)
    fh.close()


def test_truncate(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    with portalocker.Lock(tmpfile, mode='a+') as fh:
        # Make sure we didn't overwrite the original text
        fh.seek(0)
        assert fh.read(13) == 'spam and eggs'

    with portalocker.Lock(tmpfile, mode='w+') as fh:
        # Make sure we truncated the file
        assert fh.read() == ''


def test_class(tmpfile):
    lock = portalocker.Lock(tmpfile)
    lock2 = portalocker.Lock(tmpfile, fail_when_locked=False, timeout=0.01)

    with lock:
        lock.acquire()

        with pytest.raises(portalocker.LockException):
            with lock2:
                pass

    with lock2:
        pass


def test_acquire_release(tmpfile):
    lock = portalocker.Lock(tmpfile)
    lock2 = portalocker.Lock(tmpfile, fail_when_locked=False)

    lock.acquire()  # acquire lock when nobody is using it
    with pytest.raises(portalocker.LockException):
        # another party should not be able to acquire the lock
        lock2.acquire(timeout=0.01)

        # re-acquire a held lock is a no-op
        lock.acquire()

    lock.release()  # release the lock
    lock.release()  # second release does nothing


def test_rlock_acquire_release_count(tmpfile):
    lock = portalocker.RLock(tmpfile)
    # Twice acquire
    h = lock.acquire()
    assert not h.closed
    lock.acquire()
    assert not h.closed

    # Two release
    lock.release()
    assert not h.closed
    lock.release()
    assert h.closed


def test_rlock_acquire_release(tmpfile):
    lock = portalocker.RLock(tmpfile)
    lock2 = portalocker.RLock(tmpfile, fail_when_locked=False)

    lock.acquire()  # acquire lock when nobody is using it
    with pytest.raises(portalocker.LockException):
        # another party should not be able to acquire the lock
        lock2.acquire(timeout=0.01)

    # Now acquire again
    lock.acquire()

    lock.release()  # release the lock
    lock.release()  # second release does nothing


def test_release_unacquired(tmpfile):
    with pytest.raises(portalocker.LockException):
        portalocker.RLock(tmpfile).release()


def test_exlusive(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    fh = open(tmpfile, 'r')
    portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)

    # Make sure we can't read the locked file
    with pytest.raises(portalocker.LockException):
        with open(tmpfile, 'r') as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            fh2.read()

    # Make sure we can't write the locked file
    with pytest.raises(portalocker.LockException):
        with open(tmpfile, 'w+') as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            fh2.write('surprise and fear')

    # Make sure we can explicitly unlock the file
    portalocker.unlock(fh)
    fh.close()


def test_shared(tmpfile):
    with open(tmpfile, 'w') as fh:
        fh.write('spam and eggs')

    f = open(tmpfile, 'r')
    portalocker.lock(f, portalocker.LOCK_SH | portalocker.LOCK_NB)

    # Make sure we can read the locked file
    with open(tmpfile, 'r') as fh2:
        portalocker.lock(fh2, portalocker.LOCK_SH | portalocker.LOCK_NB)
        assert fh2.read() == 'spam and eggs'

    # Make sure we can't write the locked file
    with pytest.raises(portalocker.LockException):
        with open(tmpfile, 'w+') as fh2:
            portalocker.lock(fh2, portalocker.LOCK_EX | portalocker.LOCK_NB)
            fh2.write('surprise and fear')

    # Make sure we can explicitly unlock the file
    portalocker.unlock(f)
    f.close()


def test_blocking_timeout(tmpfile):
    flags = portalocker.LockFlags.SHARED

    with pytest.warns(UserWarning):
        with portalocker.Lock(tmpfile, timeout=5, flags=flags):
            pass

    lock = portalocker.Lock(tmpfile, flags=flags)
    with pytest.warns(UserWarning):
        lock.acquire(timeout=5)


def shared_lock(filename, **kwargs):
    with portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=False,
        flags=portalocker.LockFlags.SHARED | portalocker.LockFlags.NON_BLOCKING,
    ):
        time.sleep(0.2)
        return True


def shared_lock_fail(filename, **kwargs):
    with portalocker.Lock(
        filename,
        timeout=0.1,
        fail_when_locked=True,
        flags=portalocker.LockFlags.SHARED | portalocker.LockFlags.NON_BLOCKING,
    ):
        time.sleep(0.2)
        return True


def test_shared_processes(tmpfile):
    # Force spawning the process so we don't accidently inherit the lock
    # I'm not a 100% certain this will work correctly unfortunately... there
    # is some potential for breaking other tests
    multiprocessing.set_start_method('spawn')

    with multiprocessing.Pool(processes=2) as pool:
        for result in pool.imap_unordered(shared_lock, 3 * [tmpfile]):
            assert result is True

    with multiprocessing.Pool(processes=2) as pool:
        for result in pool.imap_unordered(shared_lock_fail, 3 * [tmpfile]):
            assert result is True
