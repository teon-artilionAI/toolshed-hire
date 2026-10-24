/**
 * A valid PNG just below the four mebibyte upload limit.
 *
 * The staging photograph check needs a real near-cap file, not a tiny sample.
 * The image is one thousand pixels square with opaque random colour, so the
 * compressed file is about four megabytes and the server has to do the real
 * decoding, re-encoding and upload work.
 */

import { deflateSync } from 'node:zlib'

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
const SIDE = 1100
const CHANNELS = 4
const BIT_DEPTH = 8
const COLOUR_TYPE_RGBA = 6
const CRC_TABLE = new Uint32Array(256)

for (let index = 0; index < CRC_TABLE.length; index += 1) {
  let value = index
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
  }
  CRC_TABLE[index] = value >>> 0
}

function crc32(bytes: Buffer): number {
  let value = 0xffffffff
  for (const byte of bytes) {
    value = CRC_TABLE[(value ^ byte) & 0xff] ^ (value >>> 8)
  }
  return (value ^ 0xffffffff) >>> 0
}

function chunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4)
  length.writeUInt32BE(data.length)
  const name = Buffer.from(type, 'ascii')
  const checksum = Buffer.alloc(4)
  checksum.writeUInt32BE(crc32(Buffer.concat([name, data])))
  return Buffer.concat([length, name, data, checksum])
}

export function nearCapPng(): Buffer {
  const width = SIDE
  const height = SIDE
  const rowBytes = width * CHANNELS + 1
  const raw = Buffer.alloc(rowBytes * height)
  let state = 0x9e3779b9

  for (let y = 0; y < height; y += 1) {
    const row = y * rowBytes
    raw[row] = 0
    for (let x = 0; x < width; x += 1) {
      state ^= state << 13
      state ^= state >>> 17
      state ^= state << 5
      const value = state >>> 0
      const pixel = row + 1 + x * CHANNELS
      raw[pixel] = value & 0xff
      raw[pixel + 1] = (value >>> 8) & 0xff
      raw[pixel + 2] = (value >>> 16) & 0xff
      raw[pixel + 3] = 0xff
    }
  }

  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header[8] = BIT_DEPTH
  header[9] = COLOUR_TYPE_RGBA
  header[10] = 0
  header[11] = 0
  header[12] = 0

  return Buffer.concat([
    SIGNATURE,
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

