/* Public source index. Artwork remains copyright of its authors / rights holders. */
'use strict';
const CHARACTER_REFERENCES = {
  "vt-ironmouse": {
    "referenceUrl": "https://www.rosuuri.com/vtubers/ironmouse",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-ironmouse.webp",
    "channelUrl": "https://www.youtube.com/@IronMouseParty",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-gawr-gura": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/gawr-gura/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-gawr-gura.webp",
    "channelUrl": "https://www.youtube.com/channel/UCoSrY_IQQVpmIRZ9Xf-y93g",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-sameko-saba": {
    "referenceUrl": "https://www.youtube.com/@SamekoSaba",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-sameko-saba.webp",
    "channelUrl": "https://www.youtube.com/@SamekoSaba",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-mori-calliope": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/mori-calliope/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-mori-calliope.webp",
    "channelUrl": "https://www.youtube.com/channel/UCL_qhgtOy0dy1Agp8vkySQg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-takanashi-kiara": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/takanashi-kiara/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-takanashi-kiara.webp",
    "channelUrl": "https://www.youtube.com/channel/UCHsx4Hqa-1ORjQTh9TYDhww",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-ninomae-ina-nis": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/ninomae-inanis/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-ninomae-ina-nis.webp",
    "channelUrl": "https://www.youtube.com/channel/UCMwGHR0BTZuLsmjY_NT5Pwg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-watson-amelia": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/watson-amelia/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-watson-amelia.webp",
    "channelUrl": "https://www.youtube.com/channel/UCyl1z3jo3XHR1riLFKG5UAg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-irys": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/irys/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-irys.webp",
    "channelUrl": "https://www.youtube.com/channel/UC8rcEBzJSleTkf_-agPM20g",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-ceres-fauna": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/ceres-fauna/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-ceres-fauna.webp",
    "channelUrl": "https://www.youtube.com/channel/UCO_aKKYxn4tvrqPjcTzZ6EQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-ouro-kronii": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/ouro-kronii/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-ouro-kronii.webp",
    "channelUrl": "https://www.youtube.com/channel/UCmbs8T6MWqUHP1tIQvSgKrg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-nanashi-mumei": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/nanashi-mumei/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-nanashi-mumei.webp",
    "channelUrl": "https://www.youtube.com/channel/UC3n5uGu18FoCy23ggWWp8tA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-hakos-baelz": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/hakos-baelz/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-hakos-baelz.webp",
    "channelUrl": "https://www.youtube.com/channel/UCgmPnx-EEeOrZSg5Tiw7ZRQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-tsukumo-sana": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/tsukumo-sana/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-tsukumo-sana.webp",
    "channelUrl": "https://www.youtube.com/channel/UCsUj0dszADCGbF3gNrQEuSQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-shiori-novella": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/shiori-novella/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shiori-novella.webp",
    "channelUrl": "https://www.youtube.com/channel/UCgnfPPb9JI3e9A4cXHnWbyg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-koseki-bijou": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/koseki-bijou/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-koseki-bijou.webp",
    "channelUrl": "https://www.youtube.com/channel/UC9p_lqQ0FEDz327Vgf5JwqA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-nerissa-ravencroft": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/nerissa-ravencroft/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-nerissa-ravencroft.webp",
    "channelUrl": "https://www.youtube.com/channel/UC_sFNM0z0MWm9A6WlKPuMMg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-fuwawa-abyssgard": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/fuwawa-abyssgard/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-fuwawa-abyssgard.webp",
    "channelUrl": "https://www.youtube.com/channel/UCt9H_RpQzhxzlyBxFqrdHqA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-mococo-abyssgard": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/mococo-abyssgard/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-mococo-abyssgard.webp",
    "channelUrl": "https://www.youtube.com/channel/UCt9H_RpQzhxzlyBxFqrdHqA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-elizabeth-rose-bloodflame": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/elizabeth-rose-bloodflame/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-elizabeth-rose-bloodflame.webp",
    "channelUrl": "https://www.youtube.com/channel/UCW5uhrG1eCBYditmhL0Ykjw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-gigi-murin": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/gigi-murin/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-gigi-murin.webp",
    "channelUrl": "https://www.youtube.com/channel/UCDHABijvPBnJm7F-KlNME3w",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-cecilia-immergreen": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/cecilia-immergreen/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-cecilia-immergreen.webp",
    "channelUrl": "https://www.youtube.com/channel/UCvN5h1ShZtc7nly3pezRayg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-raora-panthera": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/raora-panthera/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-raora-panthera.webp",
    "channelUrl": "https://www.youtube.com/channel/UCl69AEx4MdqMZH7Jtsm7Tig",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-hoshimachi-suisei": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/hoshimachi-suisei/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-hoshimachi-suisei.webp",
    "channelUrl": "https://www.youtube.com/channel/UC5CwaMl1eIgY8h02uZw7u8A",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-sakura-miko": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/sakuramiko/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-sakura-miko.webp",
    "channelUrl": "https://www.youtube.com/channel/UC-hM6YJuNYVAmUWxeIr9FeA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-tokino-sora": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/tokino-sora/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-tokino-sora.webp",
    "channelUrl": "https://www.youtube.com/channel/UCp6993wxpyDPHUpavwDFqgg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-azki": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/azki/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-azki.webp",
    "channelUrl": "https://www.youtube.com/channel/UC0TXe_LYZ4scaW2XMyi5_kw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-roboco-san": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/roboco-san/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-roboco-san.webp",
    "channelUrl": "https://www.youtube.com/channel/UCDqI2jOz0weumE8s7paEk6g",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-akai-haato": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/akai-haato/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-akai-haato.webp",
    "channelUrl": "https://www.youtube.com/channel/UC1CfXB_kRs3C-zaeTG3oGyg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-shirakami-fubuki": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/shirakami-fubuki/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shirakami-fubuki.webp",
    "channelUrl": "https://www.youtube.com/channel/UCdn5BQ06XqgXoAxIhbqw5Rg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-natsuiro-matsuri": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/natsuiro-matsuri/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-natsuiro-matsuri.webp",
    "channelUrl": "https://youtube.com/channel/UCQ0UDLQCjY0rmuxCDE38FGg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-aki-rosenthal": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/aki-rosenthal/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-aki-rosenthal.webp",
    "channelUrl": "https://www.youtube.com/channel/UCFTLzh12_nrtzqBPsTCqenA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-yozora-mel": {
    "referenceUrl": "https://hololive.wiki/wiki/Yozora_Mel",
    "referenceType": "community",
    "referenceImage": "/img/channel-avatars/unavailable.svg",
    "channelUrl": "",
    "channelAvatarStatus": "unresolved"
  },
  "vt-minato-aqua": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/minato-aqua/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-minato-aqua.webp",
    "channelUrl": "https://www.youtube.com/channel/UC1opHUrw8rvnsadT-iGp7Cg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-murasaki-shion": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/murasaki-shion/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-murasaki-shion.webp",
    "channelUrl": "https://www.youtube.com/channel/UCXTpFs_3PqI41qX2d9tL2Rw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-nakiri-ayame": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/nakiri-ayame/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-nakiri-ayame.webp",
    "channelUrl": "https://www.youtube.com/channel/UC7fk0CB07ly8oSl0aqKkqFg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-yuzuki-choco": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/yuzuki-choco/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-yuzuki-choco.webp",
    "channelUrl": "https://www.youtube.com/channel/UC1suqwovbL1kzsoaZgFZLKg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-oozora-subaru": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/oozora-subaru/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-oozora-subaru.webp",
    "channelUrl": "https://www.youtube.com/channel/UCvzGlP9oQwU--Y0r9id_jnA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-ookami-mio": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/ookami-mio/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-ookami-mio.webp",
    "channelUrl": "https://www.youtube.com/channel/UCp-5t9SrOQwXMU7iIjQfARg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-nekomata-okayu": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/nekomata-okayu/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-nekomata-okayu.webp",
    "channelUrl": "https://www.youtube.com/channel/UCvaTdHTWBGv3MKj3KVqJVCw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-inugami-korone": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/inugami-korone/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-inugami-korone.webp",
    "channelUrl": "https://www.youtube.com/channel/UChAnqc_AY5_I3Px5dig3X1Q",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-usada-pekora": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/usada-pekora/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-usada-pekora.webp",
    "channelUrl": "https://www.youtube.com/channel/UC1DCedRgGHBdm81E1llLhOQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-uruha-rushia": {
    "referenceUrl": "https://hololive.wiki/wiki/Uruha_Rushia",
    "referenceType": "community",
    "referenceImage": "/img/channel-avatars/unavailable.svg",
    "channelUrl": "",
    "channelAvatarStatus": "unresolved"
  },
  "vt-shiranui-flare": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/shiranui-flare/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shiranui-flare.webp",
    "channelUrl": "https://www.youtube.com/channel/UCvInZx9h3jC2JzsIzoOebWg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-shirogane-noel": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/shirogane-noel/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shirogane-noel.webp",
    "channelUrl": "https://www.youtube.com/channel/UCdyqAaZDKHXg4Ahi7VENThQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-houshou-marine": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/houshou-marine/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-houshou-marine.webp",
    "channelUrl": "https://www.youtube.com/channel/UCCzUftO8KOVkV4wQG1vkUvg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-amane-kanata": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/amane-kanata/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-amane-kanata.webp",
    "channelUrl": "https://www.youtube.com/channel/UCZlDXzGoo7d44bwdNObFacg",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-kiryu-coco": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/kiryu-coco/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-kiryu-coco.webp",
    "channelUrl": "https://www.youtube.com/channel/UCS9uQI-jC3DE0L4IpXyvr6w",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-tsunomaki-watame": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/tsunomaki-watame/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-tsunomaki-watame.webp",
    "channelUrl": "https://www.youtube.com/channel/UCqm3BQLlJfvkTsX_hvm0UmA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-tokoyami-towa": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/tokoyami-towa/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-tokoyami-towa.webp",
    "channelUrl": "https://www.youtube.com/channel/UC1uv2Oq6kNxgATlCiez59hw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-himemori-luna": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/himemori-luna/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-himemori-luna.webp",
    "channelUrl": "https://www.youtube.com/channel/UCa9Y57gfeY0Zro_noHRVrnw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-yukihana-lamy": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/yukihana-lamy/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-yukihana-lamy.webp",
    "channelUrl": "https://www.youtube.com/channel/UCFKOVgVbGmX65RxO3EtH3iw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-momosuzu-nene": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/momosuzu-nene/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-momosuzu-nene.webp",
    "channelUrl": "https://www.youtube.com/channel/UCAWSyEs_Io8MtpY3m-zqILA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-shishiro-botan": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/shishiro-botan/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shishiro-botan.webp",
    "channelUrl": "https://www.youtube.com/channel/UCUKD-uaobj9jiqB-VXt71mA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-omaru-polka": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/omaru-polka/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-omaru-polka.webp",
    "channelUrl": "https://www.youtube.com/channel/UCK9V2B22uJYu3N7eR_BT9QA",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-mano-aloe": {
    "referenceUrl": "https://hololive.wiki/wiki/Mano_Aloe",
    "referenceType": "community",
    "referenceImage": "/img/channel-avatars/unavailable.svg",
    "channelUrl": "",
    "channelAvatarStatus": "unresolved"
  },
  "vt-la-darknesss": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/la-darknesss/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-la-darknesss.webp",
    "channelUrl": "https://www.youtube.com/channel/UCENwRMx5Yh42zWpzURebzTw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-takane-lui": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/takane-lui/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-takane-lui.webp",
    "channelUrl": "https://www.youtube.com/channel/UCs9_O1tRPMQTHQ-N_L6FU2g",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-hakui-koyori": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/hakui-koyori/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-hakui-koyori.webp",
    "channelUrl": "https://www.youtube.com/channel/UC6eWCld0KwmyHFbAqK3V-Rw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-sakamata-chloe": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/sakamata-chloe/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-sakamata-chloe.webp",
    "channelUrl": "https://www.youtube.com/channel/UCIBY1ollUsauvVi4hW4cumw",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-kazama-iroha": {
    "referenceUrl": "https://hololive.hololivepro.com/en/talents/kazama-iroha/",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-kazama-iroha.webp",
    "channelUrl": "https://www.youtube.com/channel/UC_vMYWcDjmfdpH6r4TTn1MQ",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-kson": {
    "referenceUrl": "https://www.youtube.com/@ksonONAIR",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-kson.webp",
    "channelUrl": "https://www.youtube.com/@ksonONAIR",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-henya-the-genius": {
    "referenceUrl": "https://www.youtube.com/@henyathegenius",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-henya-the-genius.webp",
    "channelUrl": "https://www.youtube.com/@henyathegenius",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-projekt-melody": {
    "referenceUrl": "https://www.youtube.com/@ProjektMelody",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-projekt-melody.webp",
    "channelUrl": "https://www.youtube.com/@ProjektMelody",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-zentreya": {
    "referenceUrl": "https://www.youtube.com/@Zentreya",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-zentreya.webp",
    "channelUrl": "https://www.youtube.com/@Zentreya",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-nyanners": {
    "referenceUrl": "https://www.youtube.com/@Nyanners",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-nyanners.webp",
    "channelUrl": "https://www.youtube.com/@Nyanners",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-silvervale": {
    "referenceUrl": "https://www.youtube.com/@Silvervale",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-silvervale.webp",
    "channelUrl": "https://www.youtube.com/@Silvervale",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-veibae": {
    "referenceUrl": "https://www.youtube.com/@Veibae",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-veibae.webp",
    "channelUrl": "https://www.youtube.com/@Veibae",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-froot": {
    "referenceUrl": "https://www.youtube.com/@ApricotFroot",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-froot.webp",
    "channelUrl": "https://www.youtube.com/@ApricotFroot",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-haruka-karibu": {
    "referenceUrl": "https://www.youtube.com/@HarukaKaribu",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-haruka-karibu.webp",
    "channelUrl": "https://www.youtube.com/@HarukaKaribu",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-matara-kan": {
    "referenceUrl": "https://www.youtube.com/@MataraKan",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-matara-kan.webp",
    "channelUrl": "https://www.youtube.com/@MataraKan",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-michi-mochievee": {
    "referenceUrl": "https://www.youtube.com/@MichiMochievee",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-michi-mochievee.webp",
    "channelUrl": "https://www.youtube.com/@MichiMochievee",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-kuro-kurenai": {
    "referenceUrl": "https://www.youtube.com/@K9KURO",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-kuro-kurenai.webp",
    "channelUrl": "https://www.youtube.com/@K9KURO",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-shylily": {
    "referenceUrl": "https://www.youtube.com/@Shylily",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-shylily.webp",
    "channelUrl": "https://www.youtube.com/@Shylily",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-bao-the-whale": {
    "referenceUrl": "https://www.youtube.com/@baovtuber",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-bao-the-whale.webp",
    "channelUrl": "https://www.youtube.com/@baovtuber",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-sinder": {
    "referenceUrl": "https://www.youtube.com/@SinderVTuber",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-sinder.webp",
    "channelUrl": "https://www.youtube.com/@SinderVTuber",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-filian": {
    "referenceUrl": "https://www.twitch.tv/filian",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-filian.webp",
    "channelUrl": "https://www.youtube.com/@filianislost",
    "channelAvatarStatus": "verified-channel-avatar"
  },
  "vt-neuro-sama": {
    "referenceUrl": "https://www.youtube.com/@Neurosama",
    "referenceType": "official",
    "referenceImage": "/img/channel-avatars/vt-neuro-sama.webp",
    "channelUrl": "https://www.youtube.com/@Neurosama",
    "channelAvatarStatus": "verified-channel-avatar"
  }
};
Object.entries(CHARACTER_REFERENCES).forEach(([id,ref])=>Object.assign(SKETCH_SKINS[id],ref));
