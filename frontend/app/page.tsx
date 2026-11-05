import { Search } from "@/components/search";

export default function Home() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-6 text-3xl font-semibold">Concert Scout</h1>
      <Search />
    </main>
  );
}
