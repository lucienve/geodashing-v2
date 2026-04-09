import js from "@eslint/js";
import globals from "globals";

export default [
    js.configs.recommended,
    {
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                ...globals.browser,
                ...globals.node,
                google: "readonly",
                dataLayer: "readonly",
                API: "writable",
                map: "writable",
                markerClusterer: "readonly"
            }
        },
        rules: {
            "no-unused-vars": ["warn", { 
                "argsIgnorePattern": "^_",
                "varsIgnorePattern": "^_",
                "caughtErrorsIgnorePattern": "^_"
            }],
            "no-undef": "error"
        }
    }
];
