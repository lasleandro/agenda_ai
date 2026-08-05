"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  MapPin,
  Pencil,
  Phone,
  Search,
  UserPlus,
  Users,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AddToGroupDialog } from "@/components/ontology/add-to-group-dialog";
import { RecurringGroupDialog } from "@/components/ontology/recurring-group-dialog";
import { GroupsTab } from "@/components/ontology/groups-tab";
import {
  addSlotParticipant,
  fetchContacts,
  fetchPlaces,
  fetchRecurringSlots,
} from "@/lib/api";
import { CONTACT_LEVEL_LABELS } from "@/lib/ontology-utils";
import type { ContactSummary, Place, RecurringSlot } from "@/lib/types";

const PAGE_SIZE = 10;

export default function ClientesPage() {
  const router = useRouter();
  const [contacts, setContacts] = useState<ContactSummary[] | null>(null);
  const [groups, setGroups] = useState<RecurringSlot[] | null>(null);
  const [activeTab, setActiveTab] = useState<"clients" | "groups">("clients");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [addToGroupContact, setAddToGroupContact] = useState<ContactSummary | null>(null);
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);

  useEffect(() => {
    Promise.all([fetchContacts(), fetchPlaces(), fetchRecurringSlots()]).then(
      ([contactRes, placeRes, slotRes]) => {
        setContacts(contactRes.contacts);
        setPlaces(placeRes.places);
        setGroups(slotRes.slots.filter((slot) => slot.class_type === "group"));
      }
    );
  }, []);

  const filtered = useMemo(() => {
    if (!contacts) return [];
    const q = query.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter(
      (c) =>
        c.display_name.toLowerCase().includes(q) ||
        (c.phone ?? "").toLowerCase().includes(q) ||
        (c.home_place_name ?? "").toLowerCase().includes(q)
    );
  }, [contacts, query]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageStart = (page - 1) * PAGE_SIZE;
  const paginatedContacts = filtered.slice(pageStart, pageStart + PAGE_SIZE);
  const selectedContacts = contacts?.filter((contact) => selectedIds.has(contact.id)) ?? [];

  function toggleContact(contactId: string) {
    setNotice(null);
    const next = new Set(selectedIds);
    if (next.has(contactId)) {
      next.delete(contactId);
      setSelectedIds(next);
      return;
    }
    if (next.size === 4) {
      setNotice({ message: "Um grupo pode ter no máximo 4 clientes.", error: true });
      return;
    }
    next.add(contactId);
    setSelectedIds(next);
  }

  function addContactToGroup(contact: ContactSummary, group: RecurringSlot) {
    setAddToGroupContact(null);
    setGroups((current) =>
      current?.map((item) =>
        item.id === group.id
          ? { ...item, participant_count: item.participant_count + 1 }
          : item
      ) ?? null
    );
    setNotice({
      message: `${contact.display_name} foi adicionado a ${group.label || "Grupo"}.`,
      error: false,
    });

    void addSlotParticipant(group.id, contact.id).catch((caught) => {
      setGroups((current) =>
        current?.map((item) =>
          item.id === group.id
            ? { ...item, participant_count: Math.max(0, item.participant_count - 1) }
            : item
        ) ?? null
      );
      setNotice({
        message:
          caught instanceof Error ? caught.message : "Não foi possível adicionar ao grupo.",
        error: true,
      });
    });
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4 md:p-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Clientes</h1>
        <p className="text-sm text-muted-foreground">
          Alunos e clientes — nível, local e horário fixo.
        </p>
      </div>

      <div
        role="tablist"
        aria-label="Clientes e grupos"
        className="flex border-b border-border"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "clients"}
          onClick={() => setActiveTab("clients")}
          className={`border-b-2 px-4 py-2 text-sm font-medium ${
            activeTab === "clients"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Clientes
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "groups"}
          onClick={() => setActiveTab("groups")}
          className={`border-b-2 px-4 py-2 text-sm font-medium ${
            activeTab === "groups"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Grupos
          {groups && (
            <span className="ml-1.5 rounded-full bg-muted px-1.5 py-0.5 text-xs">
              {groups.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === "clients" ? (
        <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Buscar por nome, telefone ou local..."
            className="pl-9"
          />
        </div>
        <Button
          type="button"
          onClick={() => setGroupDialogOpen(true)}
          disabled={selectedIds.size < 1}
        >
          <Users />
          Criar grupo ({selectedIds.size})
        </Button>
      </div>

      {notice && (
        <p className={`text-sm ${notice.error ? "text-destructive" : "text-muted-foreground"}`}>
          {notice.message}
        </p>
      )}

      {contacts === null && <p className="text-sm text-muted-foreground">Carregando...</p>}

      {contacts !== null && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum cliente encontrado.</p>
      )}

      {filtered.length > 0 && (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-card">
          <div className="flex items-center gap-3 border-b border-border bg-muted/40 px-4 py-2 text-xs text-muted-foreground">
            <span>
              {selectedIds.size > 0
                ? `${selectedIds.size} de no máximo 4 selecionados`
                : "Selecionar clientes para criar um grupo"}
            </span>
            {selectedIds.size > 0 && (
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="ml-auto font-medium text-foreground hover:underline"
              >
                Limpar seleção
              </button>
            )}
          </div>
          {paginatedContacts.map((contact, i) => (
            <div
              key={contact.id}
              className={`flex items-center text-sm hover:bg-muted ${
                i !== 0 ? "border-t border-border" : ""
              }`}
            >
              <div className="pl-4">
                <input
                  type="checkbox"
                  checked={selectedIds.has(contact.id)}
                  onChange={() => toggleContact(contact.id)}
                  disabled={selectedIds.size === 4 && !selectedIds.has(contact.id)}
                  aria-label={`Selecionar ${contact.display_name}`}
                  className="h-4 w-4 rounded border-input accent-primary"
                />
              </div>
              <button
                type="button"
                onClick={() => router.push(`/clientes/${contact.id}`)}
                className="flex min-w-0 flex-1 items-center justify-between gap-4 px-4 py-3 text-left"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">
                    {contact.display_name}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {contact.phone ?? "—"}
                  </p>
                </div>
                <div className="hidden items-center gap-3 text-xs text-muted-foreground sm:flex">
                  {contact.home_place_name && (
                    <span className="flex max-w-48 items-center gap-1 truncate">
                      <MapPin className="h-3.5 w-3.5" />
                      <span className="truncate">{contact.home_place_name}</span>
                    </span>
                  )}
                  {contact.level && (
                    <span className="rounded-full bg-muted px-2 py-0.5">
                      {CONTACT_LEVEL_LABELS[contact.level] ?? contact.level}
                    </span>
                  )}
                </div>
              </button>
              <div className="flex shrink-0 items-center gap-1 pr-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setAddToGroupContact(contact)}
                  title={`Adicionar ${contact.display_name} a um grupo`}
                  aria-label={`Adicionar ${contact.display_name} a um grupo`}
                >
                  <UserPlus />
                </Button>
                {contact.phone ? (
                  <a
                    href={`tel:${contact.phone}`}
                    className={buttonVariants({ variant: "ghost", size: "icon-sm" })}
                    title={`Ligar para ${contact.display_name}`}
                    aria-label={`Ligar para ${contact.display_name}`}
                  >
                    <Phone />
                  </a>
                ) : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled
                    title="Telefone não disponível"
                    aria-label="Telefone não disponível"
                  >
                    <Phone />
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => router.push(`/clientes/${contact.id}`)}
                  title={`Ver e editar ${contact.display_name}`}
                  aria-label={`Ver e editar ${contact.display_name}`}
                >
                  <Pencil />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {filtered.length > 0 && (
        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>
            {pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, filtered.length)} de{" "}
            {filtered.length}
          </span>
          <div className="flex items-center gap-2">
            <span className="hidden sm:inline">
              Página {page} de {totalPages}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={() => setPage((current) => current - 1)}
              disabled={page === 1}
              aria-label="Página anterior"
            >
              <ChevronLeft />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={() => setPage((current) => current + 1)}
              disabled={page === totalPages}
              aria-label="Próxima página"
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}

      {groupDialogOpen && (
        <RecurringGroupDialog
          open
          onOpenChange={setGroupDialogOpen}
          contacts={selectedContacts}
          places={places}
          onPlaceCreated={(place) =>
            setPlaces((current) => [...current, place])
          }
          onCreated={(slot) => {
            setSelectedIds(new Set());
            setGroups((current) => (current ? [...current, slot] : [slot]));
            setNotice({
              message: `Grupo criado em ${slot.place_name} com ${slot.participant_count} participantes.`,
              error: false,
            });
          }}
        />
      )}
      {addToGroupContact && (
        <AddToGroupDialog
          contact={addToGroupContact}
          groups={groups ?? []}
          onOpenChange={(open) => {
            if (!open) setAddToGroupContact(null);
          }}
          onAdd={(group) => addContactToGroup(addToGroupContact, group)}
        />
      )}
        </>
      ) : (
        <GroupsTab groups={groups} />
      )}
    </div>
  );
}
