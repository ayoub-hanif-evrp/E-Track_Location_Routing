# Publish multiroute graph for CI

```bash
python scripts/pack_multiroute_graph_artifact.py

# Requires GitHub CLI authenticated to ayoub-hanif-evrp/E-Track_Location_Routing
gh release create multiroute-graph-v1 artifacts/multiroute_graph.zip \
  --title "Multiroute graph CSVs" \
  --notes "nodes/edges/road_* for nesting and physics unit tests. sha256 in artifacts/multiroute_graph.json"

# Optional secret (overrides public release URL in workflow):
# gh secret set GRAPH_ARTIFACT_URL -b"https://github.com/ayoub-hanif-evrp/E-Track_Location_Routing/releases/download/multiroute-graph-v1/multiroute_graph.zip"
```
