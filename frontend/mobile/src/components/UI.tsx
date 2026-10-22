import { useEffect, useState, type ReactNode } from "react";
import {
  View,
  Text,
  Pressable,
  TextInput,
  Modal,
  ScrollView,
  Image,
  type TextInputProps,
} from "react-native";
import { s, color } from "../styles/theme";
export const T = ({
  children,
  muted = false,
}: {
  children: ReactNode;
  muted?: boolean;
}) => <Text style={muted ? s.muted : s.text}>{children}</Text>;
export const Brand = () => (
  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
    <Image
      source={require("../../assets/octv-symbol.png")}
      style={{ width: 30, height: 30 }}
    />
    <View>
      <Text
        style={{
          color: color.fg,
          fontSize: 26,
          fontWeight: "700",
          letterSpacing: 0.5,
        }}
      >
        OCTV
      </Text>
      <Text style={{ color: color.muted, fontSize: 6, letterSpacing: 0.3 }}>
        OPEN CIRCUIT TELEVISION
      </Text>
    </View>
  </View>
);
export const Button = ({
  children,
  onPress,
  secondary = false,
  disabled = false,
}: {
  children: ReactNode;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) => (
  <Pressable
    accessibilityRole="button"
    accessibilityState={{ disabled }}
    disabled={disabled}
    onPress={onPress}
    style={({ pressed }) => [
      s.button,
      secondary && s.secondary,
      disabled && {
        backgroundColor: "#39434c",
        borderColor: "#59636b",
        opacity: 0.65,
      },
      pressed && { opacity: 0.7 },
    ]}
  >
    <Text style={s.buttonText}>{children}</Text>
  </Pressable>
);
export const Link = ({
  children,
  onPress,
}: {
  children: ReactNode;
  onPress: () => void;
}) => (
  <Pressable
    accessibilityRole="button"
    onPress={onPress}
    style={{ paddingVertical: 9 }}
  >
    <Text style={[s.text, { color: color.cyan }]}>{children}</Text>
  </Pressable>
);
export const Panel = ({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) => (
  <View style={s.panel}>
    {title && <Text style={s.h2}>{title}</Text>}
    {children}
  </View>
);
export const Pair = ({ label, value }: { label: string; value: ReactNode }) => (
  <View style={s.pair}>
    <Text style={s.muted}>{label}</Text>
    <Text style={s.value}>{value}</Text>
  </View>
);
export const Badge = ({ priority }: { priority: string }) => (
  <View
    style={[
      s.badge,
      priority === "P2" && {
        borderColor: "#d79d383d",
        backgroundColor: "#d79d381b",
      },
    ]}
  >
    <Text style={[s.badgeText, priority === "P2" && { color: "#ffd492" }]}>
      {priority}
    </Text>
  </View>
);
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <>
      <Text style={s.text}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor="#7892a4"
        style={s.input}
        autoCapitalize="none"
        autoComplete="off"
        {...props}
      />
    </>
  );
}
type ChoiceOption =
  | string
  | {
      label: string;
      value: string;
    };

function choiceValue(option: ChoiceOption): string {
  return typeof option === "string" ? option : option.value;
}

function choiceLabel(option: ChoiceOption): string {
  return typeof option === "string" ? option : option.label;
}

export function Choice({
  label,
  options,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  options: ChoiceOption[];
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}) {
  const firstValue = options[0] ? choiceValue(options[0]) : "";
  const [internalValue, setInternalValue] = useState(firstValue);
  const [open, toggle] = useState(false);

  const selectedValue = value ?? internalValue;

  useEffect(() => {
    if (value !== undefined) return;

    const exists = options.some(
      (option) => choiceValue(option) === internalValue,
    );

    if (!exists) {
      setInternalValue(firstValue);
    }
  }, [options, value, internalValue, firstValue]);

  const selected =
    options.find((option) => choiceValue(option) === selectedValue) ?? null;

  const select = (next: string) => {
    if (value === undefined) {
      setInternalValue(next);
    }

    onChange?.(next);
    toggle(false);
  };

  return (
    <View style={{ marginBottom: 16 }}>
      <T>{label}</T>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label + " 선택"}
        disabled={disabled || options.length === 0}
        onPress={() => toggle(!open)}
        accessibilityState={{
          expanded: open,
          disabled: disabled || options.length === 0,
        }}
        style={[
          s.input,
          {
            marginBottom: 0,
            flexDirection: "row",
            justifyContent: "space-between",
            alignItems: "center",
            opacity: disabled ? 0.6 : 1,
          },
        ]}
      >
        <Text style={[s.text, { flex: 1 }]}>
          {selected ? choiceLabel(selected) : "선택해주세요"}
        </Text>

        <Text style={{ color: color.muted, marginLeft: 12 }}>⌄</Text>
      </Pressable>

      {open && !disabled && (
        <View style={[s.panel, { marginBottom: 0, padding: 8 }]}>
          {options.map((option) => {
            const optionValue = choiceValue(option);

            return (
              <Link key={optionValue} onPress={() => select(optionValue)}>
                {choiceLabel(option)}
              </Link>
            );
          })}
        </View>
      )}
    </View>
  );
}
export function Segments({ options }: { options: string[] }) {
  const [active, set] = useState(options[0]);
  return (
    <View style={s.tabs}>
      {options.map((x) => (
        <Pressable
          key={x}
          accessibilityRole="button"
          accessibilityState={{ selected: active === x }}
          onPress={() => set(x)}
          style={[s.tab, active === x && s.tabActive]}
        >
          <Text style={[s.muted, active === x && { color: color.cyan }]}>
            {x}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}
export type DialogState = {
  title: string;
  body: ReactNode;
  confirm?: string;
  onConfirm?: () => void;
  cancel?: boolean;
};
export type ShowDialog = (dialog: DialogState) => void;
export function Dialog({
  value,
  close,
}: {
  value: DialogState | null;
  close: () => void;
}) {
  return (
    <Modal
      visible={!!value}
      transparent
      animationType="fade"
      onRequestClose={close}
    >
      <View style={s.overlay}>
        <View style={s.dialog}>
          <View style={s.row}>
            <Text style={s.h2}>{value?.title}</Text>
            <Link onPress={close}>×</Link>
          </View>
          <ScrollView>
            {typeof value?.body === "string" ? (
              <T>{value.body}</T>
            ) : (
              value?.body
            )}
          </ScrollView>
          {value?.cancel !== false && (
            <Button secondary onPress={close}>
              취소
            </Button>
          )}
          <Button
            onPress={() => {
              close();
              value?.onConfirm?.();
            }}
          >
            {value?.confirm || "확인"}
          </Button>
        </View>
      </View>
    </Modal>
  );
}
