/**
 * @fileoverview Modal de confirmación reutilizable.
 * Usado principalmente para confirmar eliminación de proyectos.
 */

import React, { useEffect, useRef } from "react";
import "./ConfirmModal.css";

interface ConfirmModalProps {
    isOpen: boolean;
    title: string;
    message: string;
    warningItems?: string[];
    confirmText?: string;
    cancelText?: string;
    confirmVariant?: "danger" | "primary";
    onConfirm: () => void;
    onCancel: () => void;
    children?: React.ReactNode;
}

export function ConfirmModal({
    isOpen,
    title,
    message,
    warningItems,
    confirmText = "Confirmar",
    cancelText = "Cancelar",
    confirmVariant = "danger",
    onConfirm,
    onCancel,
    children,
}: ConfirmModalProps) {
    const modalRef = useRef<HTMLDivElement>(null);
    const cancelButtonRef = useRef<HTMLButtonElement>(null);

    // Focus trap and escape key
    useEffect(() => {
        if (!isOpen) return;

        // Focus cancel button on open
        cancelButtonRef.current?.focus();

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onCancel();
            }
        };

        document.addEventListener("keydown", handleKeyDown);
        document.body.style.overflow = "hidden";

        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            document.body.style.overflow = "";
        };
    }, [isOpen, onCancel]);

    if (!isOpen) return null;

    return (
        <div className="confirm-modal-overlay" onClick={onCancel}>
            <div
                className="confirm-modal"
                ref={modalRef}
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-labelledby="confirm-modal-title"
            >
                <header className="confirm-modal__header">
                    <span className="confirm-modal__icon">⚠️</span>
                    <h2 id="confirm-modal-title" className="confirm-modal__title">
                        {title}
                    </h2>
                </header>

                <div className="confirm-modal__body">
                    <p className="confirm-modal__message">{message}</p>

                    {warningItems && warningItems.length > 0 && (
                        <div className="confirm-modal__warning">
                            <strong>Se eliminará permanentemente:</strong>
                            <ul>
                                {warningItems.map((item, index) => (
                                    <li key={index}>{item}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {children}
                </div>

                <footer className="confirm-modal__footer">
                    <button
                        type="button"
                        ref={cancelButtonRef}
                        className="confirm-modal__btn confirm-modal__btn--cancel"
                        onClick={onCancel}
                    >
                        {cancelText}
                    </button>
                    <button
                        type="button"
                        className={`confirm-modal__btn confirm-modal__btn--${confirmVariant}`}
                        onClick={onConfirm}
                    >
                        {confirmText}
                    </button>
                </footer>
            </div>
        </div>
    );
}
