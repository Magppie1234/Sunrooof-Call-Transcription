/**
 * ⚠️ MOCK DATA MODULE — content pools used only by the mock generator.
 * Real deployments replace this with AI-extraction output (see docs/07-ai-extraction-schema.md).
 */
import type { Employee, FaqCategory, ObjectionType, ActionType } from '../../types/domain';

export const EMPLOYEES: Employee[] = [
  { id: 'E01', name: 'Aarav Malhotra', team: 'North Sales', manager: 'Ritika Sethi', role: 'Sales Consultant' },
  { id: 'E02', name: 'Priya Nair', team: 'North Sales', manager: 'Ritika Sethi', role: 'Sales Consultant' },
  { id: 'E03', name: 'Kunal Bhatia', team: 'North Sales', manager: 'Ritika Sethi', role: 'Sales Consultant' },
  { id: 'E04', name: 'Sneha Kulkarni', team: 'West Sales', manager: 'Ritika Sethi', role: 'Sales Consultant' },
  { id: 'E05', name: 'Rohan Deshpande', team: 'West Sales', manager: 'Ritika Sethi', role: 'Sales Consultant' },
  { id: 'E06', name: 'Ananya Iyer', team: 'South Sales', manager: 'Vikram Chauhan', role: 'Sales Consultant' },
  { id: 'E07', name: 'Farhan Sheikh', team: 'South Sales', manager: 'Vikram Chauhan', role: 'Sales Consultant' },
  { id: 'E08', name: 'Divya Menon', team: 'Service & Care', manager: 'Vikram Chauhan', role: 'Service Executive' },
  { id: 'E09', name: 'Harpreet Singh', team: 'Service & Care', manager: 'Vikram Chauhan', role: 'Service Executive' },
  { id: 'E10', name: 'Meera Krishnamurthy-Raghunathan', team: 'South Sales', manager: 'Vikram Chauhan', role: 'Sales Consultant' },
];

export interface GeoRow { region: string; state: string; city: string; pin: string; weight: number }
export const GEO: GeoRow[] = [
  { region: 'North', state: 'Delhi NCR', city: 'New Delhi', pin: '110001', weight: 16 },
  { region: 'North', state: 'Haryana', city: 'Gurugram', pin: '122002', weight: 14 },
  { region: 'North', state: 'Uttar Pradesh', city: 'Noida', pin: '201301', weight: 9 },
  { region: 'North', state: 'Punjab', city: 'Chandigarh', pin: '160017', weight: 6 },
  { region: 'North', state: 'Rajasthan', city: 'Jaipur', pin: '302001', weight: 5 },
  { region: 'West', state: 'Maharashtra', city: 'Mumbai', pin: '400050', weight: 13 },
  { region: 'West', state: 'Maharashtra', city: 'Pune', pin: '411001', weight: 9 },
  { region: 'West', state: 'Gujarat', city: 'Ahmedabad', pin: '380015', weight: 6 },
  { region: 'South', state: 'Karnataka', city: 'Bengaluru', pin: '560034', weight: 11 },
  { region: 'South', state: 'Telangana', city: 'Hyderabad', pin: '500033', weight: 7 },
  { region: 'South', state: 'Tamil Nadu', city: 'Chennai', pin: '600028', weight: 4 },
  { region: 'East', state: 'West Bengal', city: 'Kolkata', pin: '700019', weight: 2 },
];

export const PRODUCT_SERIES = ['Lumen Kitchen', 'Essenza Kitchen', 'Verve Kitchen', 'Slim9 Kitchen', 'Wardrobe Pro', 'Accessories & Fittings'] as const;
export const LANGUAGES = ['Hindi', 'English', 'Hinglish', 'Marathi', 'Kannada'] as const;
export const LEAD_SOURCES = ['Website enquiry', 'Walk-in follow-up', 'Referral', 'Instagram ads', 'Google ads', 'Architect network', 'Existing customer'] as const;
export const CAMPAIGNS = ['Monsoon Makeover 2026', 'Premium Kitchen Fest', 'Architect Connect', 'Always-on Search', 'None'] as const;
export const CRM_STAGES = ['New', 'Contacted', 'Qualified', 'Design discussion', 'Quotation sent', 'Negotiation', 'Won', 'Lost', 'Service'] as const;
export const COMPETITORS = ['Livspace', 'HomeLane', 'Sleek', 'Häcker', 'Local carpenter', 'Godrej Interio'] as const;

export const CUSTOMER_FIRST = ['Rajesh', 'Sunita', 'Amit', 'Pooja', 'Vikas', 'Neha', 'Sanjay', 'Kavita', 'Manish', 'Ritu', 'Deepak', 'Anjali', 'Suresh', 'Lakshmi', 'Arjun', 'Shalini', 'Nitin', 'Rekha', 'Gaurav', 'Swati', 'Venkatasubramanian'] as const;
export const CUSTOMER_LAST = ['Sharma', 'Gupta', 'Verma', 'Patel', 'Reddy', 'Rao', 'Mehta', 'Joshi', 'Agarwal', 'Chopra', 'Banerjee', 'Nambiar', 'Srinivasan-Venkataraghavan', 'Khan', 'Kapoor'] as const;

export interface FaqTemplate {
  category: FaqCategory;
  standardized: string;
  variants: string[];
  answer: string;
  weight: number;
}

export const FAQ_TEMPLATES: FaqTemplate[] = [
  { category: 'Pricing & discounts', standardized: 'What is the price range for a modular kitchen?', weight: 16, answer: 'Our kitchens start around ₹4.5 lakh for the Slim9 series and go up depending on size, finish and appliances. I can share an indicative estimate after understanding your layout.', variants: ['Kitna price hoga approximately?', 'What would a 10x12 kitchen cost me?', 'Can you give me a ballpark price?'] },
  { category: 'Pricing & discounts', standardized: 'Is any discount or offer currently available?', weight: 10, answer: 'We have a festive offer on the Essenza series this month. Discounts beyond the published offer need manager approval.', variants: ['Koi offer chal raha hai kya?', 'Any festive discount going on?', 'Best price kya de sakte ho?'] },
  { category: 'Product features & benefits', standardized: 'What materials and finishes are used?', weight: 12, answer: 'We use marine-grade plywood carcasses with lacquered glass, PU or laminate shutters. All hardware is soft-close as standard.', variants: ['Which material do you use for cabinets?', 'Shutter finish kya hota hai?', 'Is the material waterproof?'] },
  { category: 'Product-series comparison', standardized: 'What is the difference between the Lumen and Essenza series?', weight: 8, answer: 'Lumen is our flagship with handle-less design and imported hardware; Essenza offers similar aesthetics with standard hardware at roughly 25% lower cost.', variants: ['Lumen aur Essenza mein kya difference hai?', 'Which series is better for my budget?', 'Compare your top two ranges please.'] },
  { category: 'Customisation', standardized: 'Can the design be customised to my layout?', weight: 8, answer: 'Yes, every kitchen is made to order. Our designer builds the layout around your slab sizes and appliance choices.', variants: ['Mere kitchen size ke hisaab se ban sakta hai?', 'Can I choose my own colours?', 'Is a corner unit possible in my layout?'] },
  { category: 'Design, drawings & measurements', standardized: 'When will I receive the design and drawings?', weight: 9, answer: 'After site measurement, the first design presentation takes 4–5 working days.', variants: ['Drawing kab milegi?', 'When can your designer visit for measurement?', 'Can you share a 3D design first?'] },
  { category: 'Installation process', standardized: 'How long does installation take and who does it?', weight: 8, answer: 'Installation is done by our own trained team and typically takes 5–7 days after material reaches site.', variants: ['Installation kaun karta hai?', 'How many days for fitting?', 'Will my house be dusty during installation?'] },
  { category: 'Delivery & project timeline', standardized: 'What is the total delivery timeline?', weight: 12, answer: 'From design freeze and advance payment, delivery is 4–6 weeks plus installation.', variants: ['Kitne din mein complete ho jayega?', 'I need it before Diwali — possible?', 'What is the lead time right now?'] },
  { category: 'Warranty & AMC', standardized: 'What warranty and AMC do you provide?', weight: 9, answer: 'We provide a 10-year warranty on cabinets and 1 year on hardware, with optional AMC plans after that.', variants: ['Warranty kitni milti hai?', 'Is there an annual maintenance contract?', 'What does the warranty cover exactly?'] },
  { category: 'Service & complaint process', standardized: 'How do I raise a service request or complaint?', weight: 7, answer: 'You can call this number or use the app; a service visit is scheduled within 48 hours in serviceable cities.', variants: ['Complaint kahan register karu?', 'My drawer channel is broken, who fixes it?', 'How fast is your service response?'] },
  { category: 'Payment & finance', standardized: 'What are the payment terms and is EMI available?', weight: 8, answer: 'Standard terms are 50% advance, 40% before dispatch and 10% after installation. EMI is available through our finance partners.', variants: ['EMI option hai kya?', 'How much advance do I need to pay?', 'Can I pay after installation?'] },
  { category: 'Product quality', standardized: 'How durable is the kitchen in Indian cooking conditions?', weight: 6, answer: 'The carcass is moisture-resistant marine ply and shutters are heat-tolerant; we test hinges for 80,000 cycles.', variants: ['Will the finish get spoiled by oil and masala?', 'Kitne saal chalega?', 'Does the laminate peel off over time?'] },
  { category: 'Serviceable locations', standardized: 'Do you deliver and install in my city?', weight: 6, answer: 'We currently serve 14 metros and satellite cities. For other locations we confirm feasibility case by case.', variants: ['Aap Indore mein service dete ho?', 'Do you work in Tier-2 cities?', 'Is installation available in my town?'] },
  { category: 'Competitor comparison', standardized: 'How are you different from Livspace/HomeLane?', weight: 6, answer: 'We are a design-led premium brand — our own factory, dedicated designers and a 10-year warranty, versus marketplace models.', variants: ['Livspace se kya better hai aap?', 'Why should I not go with a local carpenter?', 'HomeLane quoted lower — what do you say?'] },
  { category: 'Documents & process', standardized: 'What is the step-by-step buying process?', weight: 5, answer: 'Consultation, site measurement, design presentation, quotation, order confirmation with advance, production, delivery and installation.', variants: ['Process kya hota hai order karne ka?', 'What documents do I need to sign?', 'How do we start?'] },
  { category: 'Availability', standardized: 'Is the model I saw available right now?', weight: 4, answer: 'Display models are made to order; the same finish is available with a standard production timeline.', variants: ['Showroom wala model available hai?', 'Is the grey PU finish in stock?', 'Can I get it in white this month?'] },
  { category: 'Technical specifications', standardized: 'What are the technical specs of the hardware?', weight: 5, answer: 'We use Hettich/Blum soft-close hinges, tandem boxes rated to 30 kg, and 18 mm carcass boards.', variants: ['Which hinge brand do you use?', 'What is the load capacity of drawers?', 'Carcass thickness kitna hai?'] },
];

export interface ObjectionTemplate {
  type: ObjectionType;
  statement: string;
  response: string;
  technique: string;
  weight: number;
}

export const OBJECTION_TEMPLATES: ObjectionTemplate[] = [
  { type: 'Price / discount', statement: 'Your quote is quite high compared to what I expected.', response: 'I understand. Let me walk you through what is included — the warranty, hardware grade and installation — and we can also look at the Essenza series to fit your budget.', technique: 'Value reframing + downsell option', weight: 16 },
  { type: 'Budget', statement: 'My budget is only around 3 lakhs for the kitchen.', response: 'Thanks for sharing that. With Slim9 we can plan a phased approach — core kitchen now, accessories later.', technique: 'Phasing / scope adjustment', weight: 9 },
  { type: 'Timing', statement: 'We are only planning to renovate after six months.', response: 'That works — design finalisation now locks the current price, and production can start when you are ready.', technique: 'Price-lock incentive', weight: 9 },
  { type: 'Product suitability', statement: 'I am not sure a handle-less design suits my usage.', response: 'Fair point. Many families prefer the Verve series with profile handles — sturdier for heavy daily use.', technique: 'Alternative recommendation', weight: 7 },
  { type: 'Product quality', statement: 'I have heard modular kitchens do not last in Indian cooking.', response: 'That concern is common. Our carcass is marine-grade ply and we offer a 10-year warranty — I can share lab test reports.', technique: 'Evidence / proof points', weight: 7 },
  { type: 'Trust', statement: 'How do I know you will deliver on time? I have heard horror stories.', response: 'Completely fair. We share a milestone schedule in writing and delay penalties are part of our order terms.', technique: 'Written commitment', weight: 6 },
  { type: 'Installation', statement: 'I am worried installation will disturb my family for weeks.', response: 'Our own team completes installation in 5–7 days with daily cleanup — not outsourced contractors.', technique: 'Process reassurance', weight: 5 },
  { type: 'Warranty / service', statement: 'What if something breaks after two years?', response: 'Cabinets carry a 10-year warranty and we have an in-house service team with 48-hour response.', technique: 'Warranty explanation', weight: 5 },
  { type: 'Competitor preference', statement: 'HomeLane is giving me the same thing for 20% less.', response: 'I would encourage comparing the BOQ line by line — hardware brand, board grade and warranty terms usually explain the difference.', technique: 'Comparison guidance', weight: 8 },
  { type: 'Decision-maker unavailable', statement: 'I need to discuss with my wife/husband before deciding.', response: 'Of course. Shall we schedule a joint design presentation this weekend so both of you can decide together?', technique: 'Joint-meeting close', weight: 8 },
  { type: 'Serviceability', statement: 'I am in a smaller town — will you even service me there?', response: 'Let me confirm serviceability for your pin code with our operations team and revert by tomorrow.', technique: 'Verification commitment', weight: 4 },
  { type: 'Payment terms', statement: '50% advance is too much to pay upfront.', response: 'We can look at the EMI route through our finance partner, which brings the initial outflow down significantly.', technique: 'Finance option', weight: 5 },
  { type: 'Not interested', statement: 'I am not looking to buy anything right now.', response: 'No problem at all. May I send you our catalogue on WhatsApp so you have it whenever you plan?', technique: 'Soft nurture', weight: 6 },
];

export const ACTION_TYPES: ActionType[] = ['Call back', 'Send catalogue / brochure', 'Share quotation', 'Schedule meeting', 'Schedule demonstration', 'Arrange site visit', 'Share design / drawings', 'Arrange measurement', 'Provide technical clarification', 'Follow up on payment', 'Escalate complaint', 'Assign a specialist', 'Nurture the customer', 'Disqualify lead (needs approval)'];

export const NEEDS = ['New modular kitchen for under-construction flat', 'Kitchen renovation of 12-year-old home', 'Full home wardrobes + kitchen', 'Island kitchen for villa', 'Compact kitchen for 2BHK rental property', 'Replacement of carpenter-built kitchen', 'Wardrobe for master bedroom', 'Service visit for existing kitchen'] as const;

export const APPRECIATION = ['Design quality praised', 'Showroom experience appreciated', 'Designer professionalism appreciated', 'Finish and material quality praised', 'Installation team praised', 'Timely delivery appreciated'] as const;

export const DISSATISFACTION = ['Delay in receiving design/drawings', 'Quotation higher than initial estimate', 'Slow callback response', 'Service visit delayed', 'Damage during installation', 'Confusing pricing breakup', 'Follow-up too aggressive'] as const;

export const FEATURE_REQUESTS = ['Built-in dishwasher integration', 'Tall unit with appliance garage', 'Matte anti-fingerprint finish', 'Corner carousel unit', 'Breakfast counter extension', 'Under-cabinet lighting'] as const;

export const EXPECTATIONS = ['Wants single point of contact', 'Expects design in under a week', 'Wants itemised quotation', 'Expects installation before festival', 'Wants site supervision during installation'] as const;

export const PAIN_POINTS = ['Previous vendor abandoned project midway', 'Existing kitchen has water damage', 'No storage space in current kitchen', 'Bad experience with local carpenter', 'Struggling to compare vendor quotes'] as const;

export const BUYING_SIGNALS = ['Asked for quotation', 'Asked about earliest delivery slot', 'Discussed specific finish selection', 'Asked about payment schedule', 'Requested site measurement', 'Asked to bring spouse to showroom', 'Asked for order confirmation steps'] as const;

export const RISK_POOL = ['Customer comparing three vendors actively', 'Second call with unresolved complaint', 'Mentioned cancelling if delivery slips', 'Asked for refund of design fee', 'Threatened to post negative review'] as const;

export const COMPLIANCE_POOL = [
  'Unapproved discount hinted beyond policy',
  'Delivery date promised without checking production schedule',
  'Warranty scope overstated (said "lifetime")',
  'Payment requested to personal number',
  'Customer PII repeated aloud unnecessarily',
] as const;

export const AGENT_OPENERS = [
  'Good morning! This is {agent} calling from {brand}. Am I speaking with {customer}? Is this a good time to talk for a few minutes?',
  'Hello {customer}, {agent} here from {brand} regarding your kitchen enquiry. Is now a convenient time?',
  'Hi {customer}, this is {agent} from {brand}. Thank you for visiting our studio — do you have five minutes to discuss your requirement?',
] as const;

export const CUSTOMER_OPENERS = [
  'Yes, tell me. I had enquired on your website.',
  'Haan boliye, I was expecting your call.',
  'Yes, but I only have a few minutes.',
  'Actually I was about to call you — I have a few questions.',
] as const;

export const DISCOVERY_QUESTIONS = [
  'May I know the size of your kitchen and at what stage the property is?',
  'What is prompting the change — renovation, or a new home?',
  'Have you finalised your appliance list — chimney, hob, oven?',
  'By when are you hoping to have the kitchen ready?',
  'Have you seen any of our series at the studio, or shall I walk you through the options?',
] as const;

export const CLOSERS_GOOD = [
  'So to confirm — {action}. I will send a summary on WhatsApp. Thank you for your time, {customer}!',
  'Great talking to you, {customer}. As agreed, {action}. You will hear from me by then.',
] as const;

export const CLOSERS_WEAK = [
  'Okay, think about it and let me know whenever.',
  'Fine, I will try calling some other time then.',
] as const;
