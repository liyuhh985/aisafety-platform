import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const testDir = path.dirname(fileURLToPath(import.meta.url))
const srcDir = path.resolve(testDir, '../src')

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    return entry.isDirectory() ? walk(full) : [full]
  })
}

const vueFiles = walk(srcDir)
  .filter((file) => file.endsWith('.vue'))
  .filter((file) => fs.readFileSync(file, 'utf8').includes('hazardTaxonomy'))

if (vueFiles.length === 0) {
  throw new Error('no Vue consumers of hazardTaxonomy.js found')
}

for (const file of vueFiles) {
  const source = fs.readFileSync(file, 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  if (errors.length) {
    throw new Error(`${file}: SFC parse failed: ${errors.map(String).join('; ')}`)
  }

  let bindings = {}
  if (descriptor.script || descriptor.scriptSetup) {
    const script = compileScript(descriptor, {
      id: `taxonomy-v2a-${path.basename(file)}`,
      inlineTemplate: false,
    })
    bindings = script.bindings
  }

  if (descriptor.template) {
    const result = compileTemplate({
      source: descriptor.template.content,
      filename: file,
      id: `taxonomy-v2a-${path.basename(file)}`,
      compilerOptions: {
        bindingMetadata: bindings,
      },
    })
    if (result.errors.length) {
      throw new Error(`${file}: template compile failed: ${result.errors.map(String).join('; ')}`)
    }
  }
  console.log(`compiled ${path.relative(srcDir, file)}`)
}

console.log(`hazardTaxonomy Vue consumers compiled: ${vueFiles.length}`)
