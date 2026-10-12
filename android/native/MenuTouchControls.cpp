/*
Copyright © 2018 Justin Jacobs

This file is part of FLARE.

FLARE is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

FLARE is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
FLARE.  If not, see http://www.gnu.org/licenses/
*/

#include "FontEngine.h"
#include "InputState.h"
#include "MenuTouchControls.h"
#include "Platform.h"
#include "RenderDevice.h"
#include "Settings.h"
#include "WidgetLabel.h"

#include <algorithm>
#include <cmath>
#include "SharedResources.h"

MenuTouchControls::MenuTouchControls()
	: Menu()
	, move_center(0,0)
	, move_align(Utils::ALIGN_BOTTOMLEFT)
	, main1_center(0,0)
	, main1_align(Utils::ALIGN_BOTTOMRIGHT)
	, main2_center(0,0)
	, main2_align(Utils::ALIGN_BOTTOMRIGHT)
	, skill_finger_id(-1)
	, skill_label(new WidgetLabel())
	, move_finger_id(-1)
	, attack_finger_id(-1)
	, interact_finger_id(-1)
	, move_active(false)
	, interact_pulse(false)
	, move_thumb(0,0)
	, attack_label(new WidgetLabel())
	, interact_label(new WidgetLabel())
	, move_label(new WidgetLabel())
	, prev_touch_scale(settings->touch_scale)
{
	visible = true;
	skill_label->setText("Навык");
	skill_label->setJustify(FontEngine::JUSTIFY_CENTER);
	skill_label->setVAlign(LabelInfo::VALIGN_CENTER);
	attack_label->setText("Атаковать");
	interact_label->setText("Использовать");
	move_label->setText("Движение");
	attack_label->setJustify(FontEngine::JUSTIFY_CENTER);
	interact_label->setJustify(FontEngine::JUSTIFY_CENTER);
	move_label->setJustify(FontEngine::JUSTIFY_CENTER);
	attack_label->setVAlign(LabelInfo::VALIGN_CENTER);
	interact_label->setVAlign(LabelInfo::VALIGN_CENTER);
	move_label->setVAlign(LabelInfo::VALIGN_CENTER);
	align();
}

void MenuTouchControls::alignInput(Point& center, const Point& center_base, const int radius, const int _align) {
	Rect input_rect;
	input_rect.x = center_base.x - radius;
	input_rect.y = center_base.y - radius;
	input_rect.w = input_rect.h = radius;

	Utils::alignToScreenEdge(_align, &input_rect);
	center.x = input_rect.x + radius;
	center.y = input_rect.y + radius;
}

void MenuTouchControls::align() {
	move_radius = static_cast<int>(settings->view_h / 4 * settings->touch_scale);
	move_center_base.x = move_radius;
	move_center_base.y = -(move_radius / 2);
	move_deadzone = static_cast<int>(settings->view_h / 20 * settings->touch_scale);

	main1_radius = static_cast<int>(settings->view_h / 6 * settings->touch_scale);
	main1_center_base.x = -main1_radius - static_cast<int>((settings->view_h / 4) * settings->touch_scale);
	main1_center_base.y = static_cast<int>((settings->view_h / 8) * settings->touch_scale * -1);

	main2_radius = static_cast<int>(settings->view_h / 6 * settings->touch_scale);
	main2_center_base.x = 0;
	main2_center_base.y = static_cast<int>((settings->view_h / 6) * settings->touch_scale * -1);

	radius_padding = static_cast<int>(settings->view_h / 20 * settings->touch_scale);
	skill_radius = static_cast<int>(settings->view_h / 8 * settings->touch_scale);

	alignInput(move_center, move_center_base, move_radius, move_align);
	alignInput(main1_center, main1_center_base, main1_radius, main1_align);
	alignInput(main2_center, main2_center_base, main2_radius, main2_align);
	// Above the Use ring, clear of the action bar and the Attack ring.
	skill_center.x = main1_center.x;
	skill_center.y = std::max(skill_radius, main1_center.y - main1_radius - skill_radius - radius_padding);
}

void MenuTouchControls::logic() {
	// The default engine has only one synthetic mouse position, which breaks
	// simultaneous thumb movement and attack. Track real SDL finger IDs.
	if (!visible || !settings->touchscreen || settings->mouse_move) {
		move_finger_id = attack_finger_id = interact_finger_id = skill_finger_id = -1;
		move_active = false;
		if (interact_pulse) {
			inpt->pressing[Input::ACCEPT] = false;
			interact_pulse = false;
		}
		inpt->pressing[Input::MAIN2] = false;
		return;
	}

	if (settings->touch_scale != prev_touch_scale) {
		align();
		prev_touch_scale = settings->touch_scale;
	}

	inpt->pressing[Input::LEFT] = inpt->pressing[Input::RIGHT] =
		inpt->pressing[Input::UP] = inpt->pressing[Input::DOWN] = false;
	inpt->pressing[Input::MAIN2] = false;
	if (interact_pulse) {
		inpt->pressing[Input::ACCEPT] = false;
		interact_pulse = false;
	}

	bool move_found = false;
	bool attack_found = false;
	bool interact_found = false;
	bool skill_found = false;
	// First look for fingers already claimed by one of the controls.
	for (size_t i = 0; i < inpt->touchFingerCount(); ++i) {
		long int id = inpt->touchFingerId(i);
		if (id == move_finger_id) {
			move_thumb = inpt->touchFingerPosition(i);
			move_found = true;
		}
		if (id == attack_finger_id) attack_found = true;
		if (id == interact_finger_id) interact_found = true;
		if (id == skill_finger_id) skill_found = true;
	}
	if (!move_found) {
		move_finger_id = -1;
		move_active = false;
	}
	if (!attack_found) attack_finger_id = -1;
	if (!interact_found) interact_finger_id = -1;
	if (!skill_found) skill_finger_id = -1;

	// Claim new contacts only in their starting areas. A movement thumb
	// that drifts onto a right-hand button must never fire an attack.
	for (size_t i = 0; i < inpt->touchFingerCount(); ++i) {
		const long int id = inpt->touchFingerId(i);
		if (id == move_finger_id || id == attack_finger_id || id == interact_finger_id || id == skill_finger_id) continue;
		Point pos = inpt->touchFingerPosition(i);
		FPoint finger(static_cast<float>(pos.x), static_cast<float>(pos.y));
		FPoint action(static_cast<float>(main1_center.x), static_cast<float>(main1_center.y));
		FPoint attack(static_cast<float>(main2_center.x), static_cast<float>(main2_center.y));
		FPoint skill(static_cast<float>(skill_center.x), static_cast<float>(skill_center.y));
		if (skill_finger_id == -1 && Utils::isWithinRadius(skill, static_cast<float>(skill_radius), finger)) {
			skill_finger_id = id;
		}
		else if (attack_finger_id == -1 && Utils::isWithinRadius(attack, static_cast<float>(main2_radius), finger)) {
			attack_finger_id = id;
		}
		else if (interact_finger_id == -1 && Utils::isWithinRadius(action, static_cast<float>(main1_radius), finger)) {
			interact_finger_id = id;
			// Original Flare ACCEPT handles nearby items and NPCs.
			// Deliver one key press, not a repeated pickup every frame.
			inpt->pressing[Input::ACCEPT] = true;
			inpt->lock[Input::ACCEPT] = false;
			interact_pulse = true;
		}
		else if (move_finger_id == -1 && pos.x < settings->view_w * 42 / 100 &&
				 pos.y > settings->view_h * 30 / 100) {
			move_finger_id = id;
			move_active = true;
			move_center = pos; // Floating thumbstick originates at touch-down.
			move_thumb = pos;
		}
	}

	if (move_active) {
		int dx = move_thumb.x - move_center.x;
		int dy = move_thumb.y - move_center.y;
		const int max_offset = std::max(1, move_radius - radius_padding);
		float dist = std::sqrt(static_cast<float>(dx * dx + dy * dy));
		if (dist > max_offset) {
			float overflow = dist - static_cast<float>(max_offset);
			move_center.x += static_cast<int>(overflow * dx / dist);
			move_center.y += static_cast<int>(overflow * dy / dist);
			// Keep the floating base in the left/bottom gameplay region.
			move_center.x = std::max(move_radius, std::min(settings->view_w * 44 / 100, move_center.x));
			move_center.y = std::max(move_radius, std::min(settings->view_h - move_radius, move_center.y));
		}
		if (move_thumb.x < move_center.x - move_deadzone) inpt->pressing[Input::LEFT] = true;
		if (move_thumb.x > move_center.x + move_deadzone) inpt->pressing[Input::RIGHT] = true;
		if (move_thumb.y < move_center.y - move_deadzone) inpt->pressing[Input::UP] = true;
		if (move_thumb.y > move_center.y + move_deadzone) inpt->pressing[Input::DOWN] = true;
	}

	// Movement and action-zone taps must not also activate MAIN1/slot 10.
	// Only the dedicated skill ring may activate native MAIN1 / slot 10.
	// The skill can be cast while the left thumb is still moving.
	if (skill_finger_id != -1) {
		inpt->pressing[Input::MAIN1] = true;
		inpt->lock[Input::MAIN1] = false;
	}
	else if (move_active || attack_finger_id != -1 || interact_finger_id != -1) {
		inpt->lock[Input::MAIN1] = true;
	}
	// Only the attack ring holds native slot 11, independent of the stick.
	if (attack_finger_id != -1) {
		inpt->pressing[Input::MAIN2] = true;
		inpt->lock[Input::MAIN2] = false;
	}
}

bool MenuTouchControls::checkAllowMain1() {
	// Unlike the global synthetic mouse pointer, this is finger-specific.
	// Slot 10 is the player's assignable skill, while slot 11 attacks.
	return skill_finger_id != -1;
}

void MenuTouchControls::renderInput(const Point& center, const int radius, const Color& color) {
	render_device->drawEllipse(center.x - radius, center.y - radius, center.x + radius, center.y + radius, color, 15);
}

void MenuTouchControls::render() {
	if (!visible || !settings->touchscreen || settings->mouse_move)
		return;

	Color normal(255,255,255,225);
	Color deadzone(127,127,127,180);
	Color thumb(220,240,255,255);

	// No fixed movement ring: the base appears beneath the moving thumb.
	if (move_active) {
		renderInput(move_center, move_radius - radius_padding, normal);
		if (move_deadzone > 0) renderInput(move_center, move_deadzone, deadzone);
		renderInput(move_thumb, std::max(10, move_radius / 4), thumb);
	}

	renderInput(main1_center, main1_radius - radius_padding, normal);
	renderInput(main2_center, main2_radius - radius_padding, normal);
	renderInput(skill_center, std::max(12, skill_radius - radius_padding/2), normal);
	skill_label->setPos(skill_center.x, skill_center.y);
	skill_label->render();
	interact_label->setPos(main1_center.x, main1_center.y);
	attack_label->setPos(main2_center.x, main2_center.y);
	move_label->setPos(move_active ? move_center.x : move_radius,
		move_active ? move_center.y - move_radius : settings->view_h - move_deadzone);
	interact_label->render();
	attack_label->render();
	move_label->render();
}

MenuTouchControls::~MenuTouchControls() {
	delete skill_label;
	delete attack_label;
	delete interact_label;
	delete move_label;
}

