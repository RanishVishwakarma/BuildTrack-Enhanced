import { MotionConfig, motion, useScroll, useTransform } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  Boxes,
  BriefcaseBusiness,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  HardHat,
  Layers,
  Menu,
  ShieldCheck,
  ShoppingCart,
  Smartphone,
  Truck,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Logo as BrandLogo } from "../../../components/brand/Logo.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { ShaderHero } from "../../../components/ui/ShaderHero.jsx";
import { cn } from "../../../lib/utils.js";
import { BuildingArt } from "../components/BuildingArt.jsx";
import { CraneArt } from "../components/CraneArt.jsx";
import { ExcavatorArt } from "../components/ExcavatorArt.jsx";
import { useSmoothScroll } from "../hooks/useSmoothScroll.js";

// Construction photography from Unsplash (free to use under the Unsplash licence).
const photo = (id, width = 900) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=70`;
const PHOTOS = {
  plans: "photo-1503387762-592deb58ef4e",
  worker: "photo-1621905251189-08b45d6a269e",
  warehouse: "photo-1587293852726-70cdb56c2866",
  rebar: "photo-1504307651254-35680f356dfd",
  excavators: "photo-1517089596392-fb9a9033e05b",
  cranes: "photo-1599707254554-027aeb4deacd",
  crew: "photo-1541888946425-d81bb19240f5",
  frame: "photo-1508450859948-4e04fabaa4ea",
  craneSunset: "photo-1535732759880-bbd5c7265e3f",
};

// All copy describes features that exist in the app today.
const pillars = [
  {
    icon: Layers,
    title: "One source of truth",
    copy: "Projects, people, stock and spend live on the same record. Update it once and every team sees the change.",
  },
  {
    icon: ShieldCheck,
    title: "Accountability built in",
    copy: "Approvals, deliveries and payments record who acted and when, and each role sees only the work it owns.",
  },
  {
    icon: Smartphone,
    title: "Ready for the field",
    copy: "A responsive workspace that works on a site phone as well as an office screen, with no separate app to install.",
  },
];

const modules = [
  { icon: BriefcaseBusiness, title: "Projects", image: PHOTOS.plans, alt: "Engineer marking up construction drawings", copy: "Plan every build with budgets, timelines, milestones and tasks, and follow the whole portfolio on a live status board." },
  { icon: Users, title: "Workforce", image: PHOTOS.worker, alt: "Construction worker in a hard hat measuring a wall", copy: "Keep the roster, daily attendance, shift schedules, project allocation and payroll in step with the work." },
  { icon: Boxes, title: "Inventory", image: PHOTOS.warehouse, alt: "Warehouse shelving stocked with materials", copy: "Know what is on hand, record every movement in and out, and spot low stock before a site runs short." },
  { icon: ShoppingCart, title: "Procurement", image: PHOTOS.rebar, alt: "Crew tying steel reinforcement on a slab", copy: "Move material requests through approval, vendors, purchase orders, deliveries, invoices and payment." },
  { icon: Truck, title: "Equipment", image: PHOTOS.excavators, alt: "Excavators working on an earthworks site", copy: "See where each machine is deployed, who is responsible for it, and its full maintenance history." },
  { icon: BarChart3, title: "Reports & analytics", image: PHOTOS.cranes, alt: "Tower cranes over a high-rise under construction", copy: "Read progress, budget against committed spend, resource use and procurement at a glance, and export it." },
];

const capabilities = [
  "Material requests", "Approvals", "Vendor portal", "Purchase orders", "Quality inspection", "Stock movements",
  "Daily attendance", "Shift schedules", "Payroll", "Equipment maintenance", "Milestones", "Budget analytics",
];

const onSite = [
  "Mark attendance for every crew against the daily roster",
  "Inspect deliveries on arrival, with accepted stock added automatically",
  "Assign equipment to a project and an operator, and log its maintenance",
  "Approve requests and follow progress from anywhere",
];

const workflow = [
  ["Request", "A site engineer raises a material request against a project."],
  ["Approve", "The project manager reviews it and approves or rejects it."],
  ["Source", "A vendor is assigned and accepts the request in the vendor portal."],
  ["Order", "A purchase order is generated, sent and confirmed by the vendor."],
  ["Receive", "Deliveries pass quality inspection and stock updates automatically."],
  ["Settle", "Finance verifies the invoice and records the payment."],
];

const roles = [
  ["Administrator", "User accounts, permissions and every module."],
  ["Project Manager", "Projects, crews, approvals, purchase orders and payroll."],
  ["Site Engineer", "Material requests, inventory and site resources."],
  ["Store Manager", "Deliveries, quality inspection and stock receipts."],
  ["Finance", "Invoice verification and vendor payments."],
  ["Contractor", "Projects, milestones and project status."],
  ["Worker", "Their own tasks, schedule and attendance."],
  ["Client", "Progress and reports for their own projects."],
  ["Vendor", "Assigned requests, purchase orders, dispatch and invoices."],
];

const nav = [
  ["#why", "Why BuildTrack"],
  ["#modules", "Modules"],
  ["#workflow", "Workflow"],
  ["#roles", "Roles"],
];

// Fades content up as it scrolls into view (once). Honours reduced motion via MotionConfig.
function Reveal({ children, className, delay = 0, as = "div" }) {
  const Component = motion[as];
  return (
    <Component
      className={className}
      initial={{ opacity: 0, y: 28 }}
      transition={{ duration: 0.8, delay, ease: [0.22, 1, 0.36, 1] }}
      viewport={{ once: true, margin: "-80px" }}
      whileInView={{ opacity: 1, y: 0 }}
    >
      {children}
    </Component>
  );
}

// The landing navbar and footer are black, so the logo renders in white.
function Logo() {
  return <BrandLogo className="text-white" markClassName="h-10 w-10" />;
}

function SectionHeading({ eyebrow, title, description, align = "center" }) {
  return (
    <Reveal className={cn("max-w-2xl", align === "center" && "mx-auto text-center")}>
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted">{eyebrow}</p>
      <h2 className="mt-4 text-balance font-serif text-4xl font-medium leading-[1.1] md:text-5xl">{title}</h2>
      {description ? <p className="mt-5 text-pretty text-lg leading-relaxed text-muted">{description}</p> : null}
    </Reveal>
  );
}

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [heroHeight, setHeroHeight] = useState(() => (typeof window === "undefined" ? 800 : window.innerHeight));
  useSmoothScroll();

  useEffect(() => {
    const onResize = () => setHeroHeight(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // The navbar starts transparent over the hero and fades to black as the
  // hero scrolls away (fully solid by ~55% of the hero's height).
  const { scrollY } = useScroll();
  const fadeEnd = heroHeight * 0.55;
  const headerBg = useTransform(scrollY, [0, fadeEnd], ["rgba(0,0,0,0)", "rgba(0,0,0,0.92)"]);
  const headerBorder = useTransform(scrollY, [0, fadeEnd], ["rgba(255,255,255,0)", "rgba(255,255,255,0.1)"]);
  const headerBlur = useTransform(scrollY, [0, fadeEnd], ["blur(0px)", "blur(14px)"]);
  const headerShadow = useTransform(scrollY, [0, fadeEnd], ["0 0 0 rgba(0,0,0,0)", "0 10px 30px rgba(0,0,0,0.25)"]);

  return (
    <MotionConfig reducedMotion="user">
      <div className="landing min-h-screen bg-background text-foreground">
        <motion.header
          className="chrome fixed inset-x-0 top-0 z-40 border-b"
          style={
            menuOpen
              ? { backgroundColor: "rgba(0,0,0,0.96)", borderColor: "rgba(255,255,255,0.1)" }
              : { backgroundColor: headerBg, borderColor: headerBorder, backdropFilter: headerBlur, WebkitBackdropFilter: headerBlur, boxShadow: headerShadow }
          }
        >
          <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between gap-4 px-5">
            <Link aria-label="BuildTrack home" to="/">
              <Logo />
            </Link>
            <nav aria-label="Landing sections" className="hidden items-center gap-8 md:flex">
              {nav.map(([href, label]) => (
                <a className="text-sm font-medium text-white/70 transition-colors hover:text-white" href={href} key={href}>{label}</a>
              ))}
            </nav>
            <div className="flex items-center gap-2">
              <Button as={Link} className="hidden text-white hover:bg-white/10 sm:inline-flex" to="/auth/login" variant="plain">Sign in</Button>
              <Button as={Link} className="hidden bg-white text-black hover:bg-gray-200 sm:inline-flex" to="/auth/register" variant="plain">Get started</Button>
              <Button aria-expanded={menuOpen} aria-label="Toggle navigation" className="text-white hover:bg-white/10 md:hidden" onClick={() => setMenuOpen((value) => !value)} size="icon" variant="plain">
                {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </Button>
            </div>
          </div>
          {menuOpen ? (
            <nav aria-label="Landing sections" className="border-t border-white/10 px-5 py-3 md:hidden">
              {nav.map(([href, label]) => (
                <a className="block py-3 text-sm font-medium text-white/80" href={href} key={href} onClick={() => setMenuOpen(false)}>{label}</a>
              ))}
              <div className="mt-2 grid grid-cols-2 gap-2 pb-2">
                <Button as={Link} className="border border-white/20 text-white hover:bg-white/10" to="/auth/login" variant="plain">Sign in</Button>
                <Button as={Link} className="bg-white text-black hover:bg-gray-200" to="/auth/register" variant="plain">Get started</Button>
              </div>
            </nav>
          ) : null}
        </motion.header>

        <ShaderHero
          art={
            <>
              <BuildingArt className="absolute -bottom-2 left-[3%] hidden h-[62%] max-h-[480px] text-white/20 xl:block" />
              <CraneArt className="absolute -bottom-6 right-[4%] hidden h-[78%] max-h-[620px] text-white/25 lg:block" />
            </>
          }
          description="BuildTrack brings projects, crews, materials, purchasing and equipment into one shared workspace, so the site and the office make every decision from the same facts."
          eyebrow={<><HardHat className="h-4 w-4 text-gray-200" /> Construction management, site to office</>}
          footer={
            <a aria-label="Scroll to the next section" className="mx-auto flex h-10 w-10 animate-bounce items-center justify-center rounded-full border border-white/20 text-white/70 transition-colors hover:text-white motion-reduce:animate-none" href="#why">
              <ChevronDown className="h-5 w-5" />
            </a>
          }
          title="Build with clarity, from ground to handover."
        >
          <Button as={Link} className="h-12 rounded-2xl bg-white px-6 text-base text-black shadow-lg hover:bg-gray-200" to="/auth/register" variant="plain">
            Get started <ArrowRight className="h-5 w-5" />
          </Button>
          <Button as={Link} className="h-12 rounded-2xl border border-white/30 bg-white/5 px-6 text-base text-white backdrop-blur hover:bg-white/15" to="/auth/login" variant="plain">
            Sign in to your workspace
          </Button>
        </ShaderHero>

        {/* Capability ribbon */}
        <div aria-label="Capabilities" className="overflow-hidden border-b border-white/10 bg-black py-4 text-white">
          <div className="flex w-max animate-marquee gap-10 motion-reduce:animate-none">
            {[...capabilities, ...capabilities].map((item, index) => (
              <span aria-hidden={index >= capabilities.length} className="flex items-center gap-10 whitespace-nowrap text-sm font-semibold uppercase tracking-[0.18em] text-white/70" key={`${item}-${index}`}>
                {item}
                <span className="h-1 w-1 rounded-full bg-white/40" />
              </span>
            ))}
          </div>
        </div>

        <main>
          <section className="scroll-mt-20 px-5 py-24 md:py-28" id="why">
            <div className="mx-auto max-w-6xl">
              <SectionHeading
                description="Construction runs on information that is usually scattered across spreadsheets, phone calls and paper. BuildTrack puts it in one place, organised around the project."
                eyebrow="Why BuildTrack"
                title="Less chasing. More building."
              />
              <div className="mt-16 grid gap-10 md:grid-cols-3">
                {pillars.map(({ icon: Icon, title, copy }, index) => (
                  <Reveal className="border-t border-foreground pt-6" delay={index * 0.1} key={title}>
                    <Icon className="h-6 w-6" />
                    <h3 className="mt-5 font-serif text-2xl font-medium">{title}</h3>
                    <p className="mt-3 leading-relaxed text-muted">{copy}</p>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>

          <section className="scroll-mt-20 border-t border-border bg-subtle px-5 py-24 md:py-28" id="modules">
            <div className="mx-auto max-w-6xl">
              <SectionHeading
                description="Six modules, one set of projects. A delivery, a payroll run or a budget change shows up everywhere it matters."
                eyebrow="Modules"
                title="One platform for the whole build"
              />
              <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {modules.map(({ icon: Icon, title, image, alt, copy }, index) => (
                  <Reveal as="article" className="group overflow-hidden rounded-lg border border-border bg-surface shadow-sm transition-shadow duration-500 hover:shadow-xl" delay={(index % 3) * 0.08} key={title}>
                    <div className="relative aspect-[16/10] overflow-hidden bg-subtle">
                      <img
                        alt={alt}
                        className="h-full w-full object-cover grayscale-[35%] transition duration-700 ease-out group-hover:scale-105 group-hover:grayscale-0"
                        decoding="async"
                        loading="lazy"
                        src={photo(image, 700)}
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
                      <span className="absolute bottom-3 left-3 flex h-9 w-9 items-center justify-center rounded-md bg-white/95 text-black shadow">
                        <Icon className="h-5 w-5" />
                      </span>
                    </div>
                    <div className="p-6">
                      <h3 className="font-serif text-xl font-medium">{title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-muted">{copy}</p>
                    </div>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>

          <section className="scroll-mt-20 px-5 py-24 md:py-28" id="on-site">
            <div className="mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-2">
              <Reveal className="relative">
                <div className="overflow-hidden rounded-lg shadow-xl">
                  <motion.img
                    alt="Construction crew in safety gear on site"
                    className="aspect-[4/3] w-full object-cover"
                    decoding="async"
                    initial={{ scale: 1.12 }}
                    loading="lazy"
                    src={photo(PHOTOS.crew, 1100)}
                    transition={{ duration: 1.6, ease: "easeOut" }}
                    viewport={{ once: true }}
                    whileInView={{ scale: 1 }}
                  />
                </div>
                <div className="absolute -bottom-6 -right-4 hidden w-56 overflow-hidden rounded-lg border-4 border-background shadow-xl sm:block">
                  <img alt="Steel frame of a building under construction" className="aspect-square w-full object-cover" decoding="async" loading="lazy" src={photo(PHOTOS.frame, 500)} />
                </div>
              </Reveal>
              <div>
                <SectionHeading
                  align="left"
                  description="Crews on the ground, materials arriving daily, managers who need the full picture without chasing updates. BuildTrack is shaped around how a site really runs."
                  eyebrow="On site"
                  title="Made for the jobsite, not just the boardroom"
                />
                <ul className="mt-8 space-y-4">
                  {onSite.map((item, index) => (
                    <Reveal as="li" className="flex gap-3" delay={0.1 + index * 0.08} key={item}>
                      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                      <span className="leading-relaxed">{item}</span>
                    </Reveal>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          <section className="scroll-mt-20 border-y border-border bg-subtle px-5 py-24 md:py-28" id="workflow">
            <div className="mx-auto max-w-6xl">
              <SectionHeading
                description="Six accountable steps from a site request to a settled invoice, each one recorded with who acted and when."
                eyebrow="Workflow"
                title="Purchasing, without the paper chase"
              />
              <ol className="mt-16 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {workflow.map(([title, copy], index) => (
                  <Reveal as="li" className="card flex gap-5 transition-transform duration-300 hover:-translate-y-1" delay={index * 0.07} key={title}>
                    <span className="font-serif text-4xl font-medium leading-none text-muted/50">{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <h3 className="flex items-center gap-2 font-semibold">
                        {title}
                        {index === workflow.length - 1 ? <ClipboardCheck className="h-4 w-4 text-muted" /> : null}
                      </h3>
                      <p className="mt-1.5 text-sm leading-relaxed text-muted">{copy}</p>
                    </div>
                  </Reveal>
                ))}
              </ol>
            </div>
          </section>

          <section className="scroll-mt-20 px-5 py-24 md:py-28" id="roles">
            <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <SectionHeading
                  align="left"
                  description="Nine roles, each with access to exactly the work it is responsible for. Vendors get their own portal, and clients see only their own projects."
                  eyebrow="Roles"
                  title="The right view for everyone on the job"
                />
                <ExcavatorArt className="mt-10 hidden w-full max-w-md text-foreground/30 lg:block" />
              </div>
              <dl className="divide-y divide-border border-y border-border">
                {roles.map(([role, copy], index) => (
                  <Reveal className="grid gap-1 py-4 sm:grid-cols-[180px_1fr] sm:gap-6" delay={index * 0.04} key={role}>
                    <dt className="font-semibold">{role}</dt>
                    <dd className="text-sm leading-relaxed text-muted">{copy}</dd>
                  </Reveal>
                ))}
              </dl>
            </div>
          </section>

          <section className="relative isolate overflow-hidden bg-black px-5 py-28 text-white md:py-32">
            <motion.img
              alt=""
              className="absolute inset-0 -z-20 h-full w-full object-cover"
              decoding="async"
              initial={{ scale: 1.15 }}
              loading="lazy"
              src={photo(PHOTOS.craneSunset, 1600)}
              transition={{ duration: 2, ease: "easeOut" }}
              viewport={{ once: true }}
              whileInView={{ scale: 1 }}
            />
            <div className="absolute inset-0 -z-10 bg-gradient-to-r from-black via-black/80 to-black/30" />
            <Reveal className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-8 md:flex-row md:items-center">
              <div>
                <h2 className="max-w-xl text-balance font-serif text-4xl font-medium leading-[1.1] md:text-5xl">Ready to run your next build on BuildTrack?</h2>
                <p className="mt-4 max-w-xl text-lg text-white/70">Create an account to join your team, or sign in to pick up where you left off.</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button as={Link} className="h-12 rounded-2xl bg-white px-6 text-base text-black hover:bg-gray-200" to="/auth/register" variant="plain">
                  Get started <ArrowRight className="h-5 w-5" />
                </Button>
                <Button as={Link} className="h-12 rounded-2xl border border-white/30 px-6 text-base text-white hover:bg-white/10" to="/auth/login" variant="plain">
                  Sign in
                </Button>
              </div>
            </Reveal>
          </section>
        </main>

        <footer className="chrome border-t border-white/10 bg-black px-5 py-12 text-white">
          <div className="mx-auto grid max-w-6xl gap-8 md:grid-cols-[1.5fr_1fr_1fr]">
            <div>
              <Logo />
              <p className="mt-4 max-w-sm text-sm leading-relaxed text-white/60">Construction management for teams who build: projects, people, materials and money on one record.</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/40">Explore</p>
              <nav aria-label="Footer" className="mt-4 flex flex-col gap-2 text-sm text-white/70">
                {nav.map(([href, label]) => <a className="hover:text-white" href={href} key={href}>{label}</a>)}
              </nav>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/40">Account</p>
              <div className="mt-4 flex flex-col gap-2 text-sm text-white/70">
                <Link className="hover:text-white" to="/auth/login">Sign in</Link>
                <Link className="hover:text-white" to="/auth/register">Create an account</Link>
                <Link className="hover:text-white" to="/auth/forgot-password">Reset password</Link>
              </div>
            </div>
          </div>
          <div className="mx-auto mt-10 flex max-w-6xl flex-col gap-2 border-t border-white/10 pt-6 text-xs text-white/40 sm:flex-row sm:justify-between">
            <p>© {new Date().getFullYear()} BuildTrack</p>
            <p>Photography from Unsplash</p>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
