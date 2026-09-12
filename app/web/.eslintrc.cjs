/** Mirrors monorepo-incluir/apps/frontend/.eslintrc.cjs, minus the Next.js bits. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { project: true, tsconfigRootDir: __dirname },
  plugins: ["@typescript-eslint", "react-hooks"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended-type-checked",
    "plugin:@typescript-eslint/stylistic-type-checked",
    "plugin:react-hooks/recommended",
  ],
  rules: {
    "@typescript-eslint/consistent-type-imports": [
      "warn",
      { prefer: "type-imports", fixStyle: "inline-type-imports" },
    ],
    "@typescript-eslint/no-unused-vars": ["off"],
    "react-hooks/exhaustive-deps": "off",
  },
  ignorePatterns: ["dist", "*.config.ts", "*.config.js", ".eslintrc.cjs"],
};
