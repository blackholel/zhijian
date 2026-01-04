require('@rushstack/eslint-patch/modern-module-resolution')

const vuePlugin = require('eslint-plugin-vue')

module.exports = [
  ...vuePlugin.configs['flat/essential'],
  {
    languageOptions: {
      ecmaVersion: 'latest',
    },
  },
]
