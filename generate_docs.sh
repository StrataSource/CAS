#!/bin/bash
mkdir -p generated/schemas
jsonschema2md -d schemas -o generated/schemas -x generated/schemas
echo "done! you can find the generated Markdown files in generated/schemas."
