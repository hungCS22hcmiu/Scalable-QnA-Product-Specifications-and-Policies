package cache

import (
	"crypto/rand"
	"strings"
	"time"
)

// crockford is the Crockford base32 alphabet ULIDs use (excludes I, L, O, U to avoid
// transcription errors).
const crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// NewEntryID mints a ULID: a 48-bit millisecond timestamp followed by 80 bits of randomness,
// Crockford base32 encoded to 26 characters. interfaces.md §D's Tier-1 schema names this field
// `entry_id <ulid>`; implementing the real algorithm against crypto/rand + time honors that
// literally without a fourth Go dependency beyond the three already signed off
// (a new dependency needs sign-off).
func NewEntryID() string {
	var raw [16]byte // 6 bytes timestamp + 10 bytes randomness

	ms := uint64(time.Now().UnixMilli())
	raw[0] = byte(ms >> 40)
	raw[1] = byte(ms >> 32)
	raw[2] = byte(ms >> 24)
	raw[3] = byte(ms >> 16)
	raw[4] = byte(ms >> 8)
	raw[5] = byte(ms)

	if _, err := rand.Read(raw[6:]); err != nil {
		panic("cache: crypto/rand unavailable: " + err.Error())
	}

	return encodeCrockford(raw)
}

// encodeCrockford packs 128 bits (16 bytes) into 26 base32 characters, 5 bits at a time.
func encodeCrockford(raw [16]byte) string {
	var b strings.Builder
	b.Grow(26)

	var bitBuf uint64
	bitLen := 0
	byteIdx := 0

	for b.Len() < 26 {
		for bitLen < 5 && byteIdx < 16 {
			bitBuf = (bitBuf << 8) | uint64(raw[byteIdx])
			bitLen += 8
			byteIdx++
		}
		if bitLen < 5 {
			bitBuf <<= 5 - bitLen
			bitLen = 5
		}
		bitLen -= 5
		idx := (bitBuf >> uint(bitLen)) & 0x1F
		b.WriteByte(crockford[idx])
	}
	return b.String()
}
