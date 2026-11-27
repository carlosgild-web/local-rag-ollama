/**
 * file:symbol -> the current line and a short excerpt, found by regex in the working tree.
 * No line numbers are written anywhere by hand: the stage asks this module at take time,
 * and `--check` fails when a symbol the storyboard names is gone (ported from luna-hybrid-agent).
 *
 *   node lines.mjs --check storyboard.json
 *   node lines.mjs backend/app/retrieval/fusion.py fuse_rrf_scored
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve as resolvePath } from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = resolvePath(dirname(fileURLToPath(import.meta.url)), '..')
const EXCERPT_LINES = 9

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Lines that define `name` in a Python, TypeScript or Markdown file. */
function definitionPatterns(name, file) {
  const n = escape(name)
  if (file.endsWith('.py')) {
    return [
      new RegExp(`^(\\s*)(?:async\\s+)?def ${n}\\b`),
      new RegExp(`^(\\s*)class ${n}\\b`),
      new RegExp(`^(\\s*)${n}\\s*(?::[^=]+)?=`),
    ]
  }
  if (file.endsWith('.md')) return [new RegExp(`^()#+ .*${n}`)]
  return [
    new RegExp(`^(\\s*)(?:export\\s+)?(?:default\\s+)?(?:async\\s+)?function\\*?\\s*${n}\\b`),
    new RegExp(`^(\\s*)(?:export\\s+)?(?:const|let|type|interface|class)\\s+${n}\\b`),
  ]
}

function findFrom(lines, start, name, file, minIndent) {
  const patterns = definitionPatterns(name, file)
  for (let i = start; i < lines.length; i++) {
    for (const re of patterns) {
      const m = re.exec(lines[i])
      if (m && m[1].length >= minIndent) return { index: i, indent: m[1].length }
    }
  }
  return null
}

function excerpt(lines, index, indent, file) {
  if (file.endsWith('.md')) {
    // a heading and its section, up to the next heading
    const end = lines.findIndex((l, i) => i > index && /^#+ /.test(l))
    return lines
      .slice(index, end === -1 ? undefined : end)
      .filter((l) => l.trim())
      .slice(0, EXCERPT_LINES)
      .join('\n')
  }
  const out = [lines[index]]
  for (let i = index + 1; i < lines.length && out.length < EXCERPT_LINES; i++) {
    const line = lines[i]
    const dedent = line.trim() !== '' && line.length - line.trimStart().length <= indent
    if (dedent && !/^\s*[)\]}]/.test(line)) break
    out.push(line)
  }
  while (out.length && out[out.length - 1].trim() === '') out.pop()
  const cut = Math.min(...out.filter((l) => l.trim()).map((l) => l.length - l.trimStart().length))
  return out.map((l) => l.slice(cut)).join('\n')
}

/** `symbol` may be dotted: "Recording.generate" looks for `generate` inside `Recording`. */
export function resolve(file, symbol) {
  const text = readFileSync(join(ROOT, file), 'utf8')
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  let at = { index: 0, indent: -1 }
  for (const part of symbol.split('.')) {
    const found = findFrom(lines, at.index, part, file, at.indent + 1)
    if (!found) throw new Error(`${file}: symbol "${symbol}" not found (part "${part}")`)
    at = found
  }
  return { file, symbol, line: at.index + 1, excerpt: excerpt(lines, at.index, at.indent, file) }
}

/** Every [file, symbol] the storyboard's rows name. */
export function callouts(storyboard) {
  return storyboard.rows.flatMap((row) => (row.callouts ?? []).map(([file, symbol]) => ({ row: row.id, file, symbol })))
}

function check(path) {
  const storyboard = JSON.parse(readFileSync(path, 'utf8'))
  let failed = 0
  for (const { row, file, symbol } of callouts(storyboard)) {
    try {
      const r = resolve(file, symbol)
      console.log(`ok   ${row.padEnd(5)} ${file}:${r.line}  ${symbol}`)
    } catch (err) {
      failed++
      console.log(`FAIL ${row.padEnd(5)} ${err.message}`)
    }
  }
  console.log(failed ? `\n${failed} callout(s) not found` : '\nevery callout resolves')
  process.exit(failed ? 1 : 0)
}

if (process.argv[1] && resolvePath(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [flag, a, b] = process.argv.slice(2)
  if (flag === '--check') check(a)
  else {
    const r = resolve(flag, a ?? b)
    console.log(`${r.file}:${r.line}\n${r.excerpt}`)
  }
}
