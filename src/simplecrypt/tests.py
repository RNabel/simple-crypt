# -*- coding: utf-8 -*-
from binascii import hexlify

from functools import reduce
from unittest import TestCase, main

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util import Counter
from math import sqrt

import datetime

from simplecrypt import encrypt, decrypt, _expand_keys, DecryptionException, \
    _random_bytes, HEADER, HALF_BLOCK, SALT_LEN, _assert_header_prefix, \
    _assert_header_version, LATEST, HEADER_LEN, _hide, create_cipher_storage


class TestEncryption(TestCase):
    def test_bytes_plaintext(self):
        ptext = decrypt('password', encrypt('password', b'message'))
        assert ptext == b'message', ptext

    def test_unicode_ciphertext(self):
        u_ciphertext = b'some string'.decode('utf8')
        try:
            decrypt('password', u_ciphertext)
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'bytes' in str(e), e

    def test_bytes_password(self):
        ptext = decrypt(b'password', encrypt(b'password', b'message'))
        assert ptext == b'message', ptext
        ptext = decrypt('password', encrypt(b'password', b'message'))
        assert ptext == b'message', ptext
        ptext = decrypt(b'password', encrypt('password', b'message'))
        assert ptext == b'message', ptext

    def test_unicode_plaintext(self):
        def u(string):
            u_type = type(b''.decode('utf8'))
            if not isinstance(string, u_type):
                return string.decode('utf8')
            return string

        u_message = u('message')
        u_high_order = u('¥£€$¢₡₢₣₤₥₦₧₨₩₪₫₭₮₯₹')
        ptext = decrypt('password', encrypt('password', u_message))
        assert ptext.decode('utf8') == 'message', ptext
        ptext = decrypt('password', encrypt('password', u_message.encode('utf8')))
        assert ptext == 'message'.encode('utf8'), ptext
        ptext = decrypt('password', encrypt('password', u_high_order))
        assert ptext.decode('utf8') == u_high_order, ptext
        ptext = decrypt('password', encrypt('password', u_high_order.encode('utf8')))
        assert ptext == u_high_order.encode('utf8'), ptext

    def test_pbkdf(self):
        key = PBKDF2(b'password', b'salt')
        assert key == b'n\x88\xbe\x8b\xad~\xae\x9d\x9e\x10\xaa\x06\x12$\x03O', key

    def test_expand(self):
        key1, key2 = _expand_keys('password', b'salt', 10000)
        assert key1 != key2
        assert key1 == b'^\xc0+\x91\xa4\xb5\x9coY\xdd_\xbeL\xa6I\xec\xe4\xfa\x85h\xcd\xb8\xba6\xcfABn\x88\x05R+', key1
        assert len(key1) * 8 == 256, len(key1)
        assert key2 == b'\xa4\xe2\xae\xac\x19\xa4\x82\x15\x01\xcf`\x91&\xab\x01\xdf%f\x10\x83\xbff\xf9^R\x17\xfe\xe3\x19\x85\x04\xb1', key2
        assert len(key2) * 8 == 256, len(key2)

    def test_modification(self):
        ctext = bytearray(encrypt('password', 'message'))
        ctext[10] = ctext[10] ^ 85
        try:
            decrypt('password', ctext)
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'modified' in str(e), e

    def test_bad_password(self):
        ctext = bytearray(encrypt('password', 'message'))
        try:
            decrypt('badpassword', ctext)
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'Bad password' in str(e), e

    def test_empty_password(self):
        try:
            encrypt('', 'message')
            assert False, 'expected error'
        except ValueError as e:
            assert 'password' in str(e), e

    def test_distinct(self):
        enc1 = encrypt('password', 'message')
        enc2 = encrypt('password', 'message')
        assert enc1 != enc2

    def test_length(self):
        ctext = encrypt('password', '')
        assert not decrypt('password', ctext)
        try:
            decrypt('password', bytes(bytearray(ctext)[:-1]))
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'Missing' in str(e), e
        try:
            decrypt('password', bytes(bytearray()))
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'Missing' in str(e), e

    def test_header(self):
        ctext = bytearray(encrypt('password', 'message'))
        assert ctext[:HEADER_LEN] == HEADER[LATEST]
        for i in range(len(HEADER)):
            ctext2 = bytearray(ctext)
            ctext2[i] = 1
            try:
                _assert_header_prefix(ctext2)
                _assert_header_version(ctext2)
                assert False, 'expected error'
            except DecryptionException as e:
                assert 'bad header' in str(e), e
                if i > 1:
                    assert 'more recent version of simple-crypt' in str(e), e
                else:
                    assert 'not generated by simple-crypt' in str(e)
        ctext2 = bytearray(ctext)
        ctext2[len(HEADER)] = 1
        try:
            decrypt('password', ctext2)
            assert False, 'expected error'
        except DecryptionException as e:
            assert 'format' not in str(e), e


class TestCounter(TestCase):
    def test_wraparound(self):
        # https://bugs.launchpad.net/pycrypto/+bug/1093446
        ctr = Counter.new(8, initial_value=255, allow_wraparound=False)
        try:
            ctr()
            ctr()
            assert False, 'expected error'
        except Exception as e:
            assert 'wrapped' in str(e), e
        ctr = Counter.new(8, initial_value=255, allow_wraparound=True)
        ctr()
        ctr()
        ctr = Counter.new(8, initial_value=255)
        try:
            ctr()
            ctr()
            assert False, 'expected error'
        except Exception as e:
            assert 'wrapped' in str(e), e

    def test_prefix(self):
        salt = _random_bytes(SALT_LEN[LATEST] // 8)
        ctr = Counter.new(HALF_BLOCK, prefix=salt[:HALF_BLOCK // 8])
        count = ctr()
        assert len(count) == AES.block_size, count


class TestRandBytes(TestCase):
    def test_bits(self):
        b = _random_bytes(100)  # test will fail ~ 1 in 2^100/8 times
        assert len(b) == 100
        assert 0 == reduce(lambda x, y: x & y, bytearray(b)), b
        assert 255 == reduce(lambda x, y: x | y, bytearray(b)), b

    def test_all_values(self):
        b = _random_bytes(255 * 10)
        assert reduce(lambda a, b: a and b, (n in b for n in range(256)), True)
        b = _random_bytes(255)
        assert not reduce(lambda a, b: a and b, (n in b for n in range(256)), True)

    def test_hide_mean(self):
        for l in range(0, 40):
            n = 100  # works with 10000 but takes time
            sum = [0 for _ in range(n)]
            for _ in range(n):
                rs = _random_bytes(l)
                assert len(rs) == l
                for (i, r) in enumerate(rs):
                    sum[i] += r
            for i in range(l):
                mean = sum[i] / (127.5 * n)
                assert abs(mean - 1) < 3.3 / sqrt(n), "length %d sum %d for %d samples, norm to %f" % (
                    l, sum[i], n, mean)

    def test_hide_bits(self):
        # this fails about 1 in 256 times per test (at size 1 byte)
        # so we make sure no combination of (l, i, j) fails twice
        bad = []
        for retry in range(8):
            for l in range(1, 40):
                rs = _random_bytes(l)
                h1 = _hide(rs)
                for i in range(l):
                    for j in range(8):
                        flipped = bytearray(rs)
                        assert h1 == _hide(flipped)
                        flipped[i] ^= 2 ** j
                        h2 = _hide(flipped)
                        if h1 == h2:
                            state = (l, i, j)
                            assert state not in bad, "%s %s / %s" % (state, hexlify(h1), hexlify(h2))
                            bad.append(state)


class TestBackwardsCompatibility(TestCase):
    def test_known_0(self):
        # this was generated with python 3.3 and v1.0.0
        ctext = b'sc\x00\x00;\xdf|*^\xdbK\xca\xfe?%\x95\xc0\x1a\xe3\r`\x84F\xec\xc9\x86\x00\x90\x7f\xe7\xd1\xbc\xa5\xb2\x9c\x02\xc0\xb9\xb4\x89\xc5\x95\xa9\xc0\n\xac\x01\xe7\xfb\x07i"B\xb5\xedJ\xe7\xed\x95'
        ptext = decrypt('password', ctext)
        assert ptext == b'message', ptext

    def test_known_1(self):
        # this was generated with python 3.3 and v3.0.0
        ctext = b'sc\x00\x01jX\xdc\xbdY\ra\xbf\x8e\x17\xec\xfd\xebQ\xa0\xe3\xce\x9b\xe4\xa7\xbd\x9d\x9dJ\x16\x98\x11_IU\x82L\x96\xe7\x96Q\x01\x94\xe6\xe4\xeb8\xc9\xf2\xdd<t(\xe0\xf4\x96jy\xc9\xf5\xc5\xb6\xa0\xc3@R\xd7\x7f\xed\xc0=\x18\xfcX\xf0\xf4'
        ptext = decrypt('password', ctext)
        assert ptext == b'message', ptext

    def test_known_2(self):
        # this was generated with python 3.3 and v4.0.0
        ctext = b'sc\x00\x02g)x\x7f\xbf\xc8\xe5\xff\roR\x9b\x0e#X\xb8eW=\x93,\x85I{\x9a{\x9d\x07\xf4TUj\xfek/\xed\xff\xde\xaa|\\`\x1a\xc1\xf9\x81\x12\x0blE\r$\x827\x1b\xe9Gz\xf2\x87T\xd1gW\x9ez\xd9Y{\x80\x1a'
        ptext = decrypt('password', ctext)
        assert ptext == b'message', ptext


class TestPreComputedPassword(TestCase):
    def test_pre_computed_encrypt(self):
        pw = "password"
        data = "data"
        # Calculate cipher.
        cipher_storage = create_cipher_storage(pw)

        # encrypted - pre-computed.
        encrypted_computed = encrypt(pw, data, True)

        self.assertTrue(decrypt(pw, encrypted_computed) == data)

    def test_pre_computed_decrypt(self):
        pw = "password"
        data = "data"
        # Calculate cipher.
        create_cipher_storage(pw)

        # decrypt - pre-computed.
        encrypted = encrypt(pw, data)

        self.assertTrue(decrypt(pw, encrypted, True) == data)

    def test_timing_encrypt(self):
        pw = "password"
        data = "data"

        create_cipher_storage(pw)

        curr_time = datetime.datetime.now()
        for i in range(100):
            encrypt(pw, data, True)

        curr_time = datetime.datetime.now() - curr_time
        print curr_time / 100
        curr_time = datetime.datetime.now()

        for i in range(10):
            encrypt(pw, data)

        curr_time = datetime.datetime.now() - curr_time
        print curr_time / 10

    def test_timing_decrypt(self):
        pass  # TODO finish this.


class TestCipherStorage(TestCase):
    def test_top_cipher_fails(self):
        cs = create_cipher_storage("h")
        try:
            cs.get_top_cipher()
            self.fail("No exception raised.")
        except Exception:
            pass

    def test_top_cipher_new_salt(self):
        cs = create_cipher_storage("pw")
        _salt = bytes(_random_bytes(SALT_LEN[LATEST] // 8))
        curr_time = datetime.datetime.now()
        cs.get_cipher(_salt)
        time_diff_1 = datetime.datetime.now() - curr_time

        curr_time = datetime.datetime.now()
        cs.get_cipher(_salt)
        time_diff_2 = datetime.datetime.now() - curr_time
        print time_diff_1
        print time_diff_2

        self.assertTrue(time_diff_1 > time_diff_2 * 100, "Second access too slow.")

    def test_cipher_creation(self):
        cs = create_cipher_storage("pw")

        # Test that getting tope cipher fails.
        try:
            cs.get_top_cipher()
            self.fail("Getting top cipher should fail as empty.")
        except Exception:
            pass

        cs.create_cipher()

        try:
            _salt, _hmac, _cipher_key =cs.get_top_cipher()
            self.assertTrue(_salt and _hmac and _cipher_key)

        except Exception:
            self.fail("Should return the new cipher.")

try:

    unicode()  # succeeds in 2.7


    class TestPython27Syntax(TestCase):

        def test_python27(self):
            ptext = decrypt('password', encrypt('password', 'message'))
            assert ptext == 'message', ptext
            # this needs to be commented out when testing with 3.0 (syntax error)
            ptext = decrypt(u'password', encrypt(u'password', u'message'))
            assert ptext == u'message', ptext

except NameError:

    class TestPython3Syntax(TestCase):

        def test_python3(self):
            ptext = decrypt(b'password', encrypt(b'password', b'message'))
            assert ptext == b'message', ptext
            ptext = decrypt('password', encrypt('password', 'message')).decode('utf8')
            assert ptext == 'message', ptext

if __name__ == '__main__':
    main()
