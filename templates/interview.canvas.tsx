import {
  Button,
  H1,
  Select,
  Stack,
  Text,
  TextArea,
  TextInput,
  useCanvasState,
} from "cursor/canvas";

export default function LoopKitInterview() {
  const [trigger, setTrigger] = useCanvasState("trigger", "");
  const [steps, setSteps] = useCanvasState("steps", "");
  const [mustNot, setMustNot] = useCanvasState("must_not", "");
  const [actor, setActor] = useCanvasState("actor", "cursor");
  const [allow, setAllow] = useCanvasState("allow", "");
  const [probe, setProbe] = useCanvasState("probe", "");
  const [onFail, setOnFail] = useCanvasState("on_fail", "revert");
  const [maxIter, setMaxIter] = useCanvasState("max_iterations", "");
  const [blast, setBlast] = useCanvasState("blast", "");
  const [submitted, setSubmitted] = useCanvasState("submitted", false);

  return (
    <Stack gap={14}>
      <H1>Self Improvement Loop Kit</H1>
      <Text tone="secondary">All questions. Type your own answers.</Text>
      <Text weight="semibold">What should start this loop?</Text>
      <TextInput value={trigger} onChange={setTrigger} />
      <Text weight="semibold">What should the agent do, step by step?</Text>
      <TextArea value={steps} onChange={setSteps} rows={4} />
      <Text weight="semibold">What must it not do?</Text>
      <TextArea value={mustNot} onChange={setMustNot} rows={3} />
      <Text weight="semibold">Who runs it?</Text>
      <Select
        value={actor}
        onChange={setActor}
        options={[
          { value: "cursor", label: "cursor" },
          { value: "claude-code", label: "claude-code" },
          { value: "codex", label: "codex" },
        ]}
      />
      <Text weight="semibold">Allowed verbs?</Text>
      <TextInput value={allow} onChange={setAllow} />
      <Text weight="semibold">Shell command that means healthy?</Text>
      <TextInput value={probe} onChange={setProbe} />
      <Text weight="semibold">If that command fails?</Text>
      <Select
        value={onFail}
        onChange={setOnFail}
        options={[
          { value: "revert", label: "revert" },
          { value: "stop", label: "stop" },
          { value: "page", label: "page" },
        ]}
      />
      <Text weight="semibold">Max tries?</Text>
      <TextInput value={maxIter} onChange={setMaxIter} type="number" />
      <Text weight="semibold">Blast radius?</Text>
      <TextInput value={blast} onChange={setBlast} />
      <Button
        variant="primary"
        disabled={submitted}
        onClick={() => setSubmitted(true)}
      >
        Submit
      </Button>
      {submitted ? (
        <Text tone="secondary">Saved. The agent will emit next.</Text>
      ) : null}
    </Stack>
  );
}
