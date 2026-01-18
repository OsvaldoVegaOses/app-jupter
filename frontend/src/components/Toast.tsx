import { useEffect, useState } from "react";
import "./Toast.css";

export interface ToastMessage {
    id: string;
    type: "success" | "error" | "info";
    message: string;
}

interface ToastProps {
    messages: ToastMessage[];
    onDismiss: (id: string) => void;
}

export function Toast({ messages, onDismiss }: ToastProps) {
    return (
        <div className="toast-container">
            {messages.map((msg) => (
                <ToastItem key={msg.id} message={msg} onDismiss={onDismiss} />
            ))}
        </div>
    );
}

function ToastItem({
    message,
    onDismiss,
}: {
    message: ToastMessage;
    onDismiss: (id: string) => void;
}) {
    const [visible, setVisible] = useState(true);

    useEffect(() => {
        const timer = setTimeout(() => {
            setVisible(false);
            setTimeout(() => onDismiss(message.id), 300);
        }, 4000);
        return () => clearTimeout(timer);
    }, [message.id, onDismiss]);

    return (
        <div
            className={`toast toast--${message.type} ${visible ? "toast--visible" : "toast--hidden"}`}
            onClick={() => onDismiss(message.id)}
        >
            <span className="toast__icon">
                {message.type === "success" && "✓"}
                {message.type === "error" && "✗"}
                {message.type === "info" && "ℹ"}
            </span>
            <span className="toast__message">{message.message}</span>
        </div>
    );
}
