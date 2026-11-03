import parser from '@babel/eslint-parser'
import hooks from 'eslint-plugin-react-hooks'
import refresh from 'eslint-plugin-react-refresh'
export default [{ ignores: ['dist/**', 'node_modules/**'] }, {
  files: ['src/**/*.{ts,tsx}'],
  languageOptions: { parser, parserOptions: { requireConfigFile: false, babelOptions: { presets: [['@babel/preset-typescript', {allExtensions:true,isTSX:true}]] } } },
  plugins: {'react-hooks':hooks,'react-refresh':refresh},
  rules: {'react-hooks/rules-of-hooks':'error','react-hooks/exhaustive-deps':'error','react-refresh/only-export-components':['error',{allowConstantExport:true}]}
}]
