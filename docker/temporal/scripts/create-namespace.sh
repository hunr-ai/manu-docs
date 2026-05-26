set -eu

until temporal operator namespace describe --namespace "$DEFAULT_NAMESPACE" --address "$TEMPORAL_ADDRESS" >/dev/null 2>&1; do
  if temporal operator namespace create --namespace "$DEFAULT_NAMESPACE" --address "$TEMPORAL_ADDRESS"; then
    break
  fi
  sleep 2
done