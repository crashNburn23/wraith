import js from "@eslint/js";
import globals from "globals";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";

const unusedVarsRule = ["warn", {
  argsIgnorePattern: "^_",
  varsIgnorePattern: "^_",
  caughtErrorsIgnorePattern: "^_",
}];

export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: {
      react: reactPlugin,
      "react-hooks": reactHooks,
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...reactPlugin.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",       // project uses runtime duck-typing, not PropTypes
      "no-unused-vars": unusedVarsRule,
      // react-hooks v7 rules that are too strict for this codebase's valid patterns:
      "react-hooks/set-state-in-effect": "off",  // resetting state on prop change is documented valid
      "react-hooks/immutability": "off",          // forward refs in closures work at runtime
    },
  },
  {
    // Test files — add vitest/node globals and relax some rules
    files: ["src/__tests__/**/*.{js,jsx}", "src/test/**/*.{js,jsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.node,   // provides `global`
      },
    },
    rules: {
      "no-unused-vars": unusedVarsRule,
    },
  },
];
